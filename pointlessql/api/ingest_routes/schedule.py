"""Phase 82.3 — cron schedule control for an ingest source.

``PUT /api/ingest/sources/{id}/schedule`` accepts
``{"cron_expr": str}`` to create / update or
``{"cron_expr": null}`` to unschedule.

The schedule lives on a ``Job`` row (``kind="ingest_pull"``,
``config={"source_id", "mapping_index"}``).  Because PointlesSQL's
scheduler scopes by single-mapping ``Job`` rows, multi-mapping
sources need one Job per mapping.  v1 simplification: we create ONE
Job that points at ``mapping_index=0``; the scheduler tick fires
``run_pull(mapping_index=0)``; the executor then loops through all
remaining mappings in :func:`_chain_remaining_mappings`.  This keeps
the Job-table surface minimal at the cost of a small executor-side
loop.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from croniter import croniter
from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.models import IngestSource, Job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "schedule"])


def _valid_cron(expr: str) -> bool:
    """Best-effort cron validation via :class:`croniter.croniter`."""
    try:
        croniter(expr)
        return True
    except (ValueError, KeyError):
        return False


@router.put("/api/ingest/sources/{source_id}/schedule")
async def api_put_schedule(
    request: Request,
    source_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Set or clear the source's pull schedule.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.
        body: ``{"cron_expr": "0 2 * * *"}`` to schedule, or
            ``{"cron_expr": null}`` to unschedule.

    Returns:
        ``{"ok": True, "job_id": int | None, "cron_expr": str | None}``.

    Raises:
        HTTPException: 400 on invalid cron; 404 on missing source.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    raw_expr = body.get("cron_expr")
    cron_expr: str | None
    if raw_expr is None:
        cron_expr = None
    else:
        cron_expr = str(raw_expr).strip()
        if not cron_expr:
            cron_expr = None
    if cron_expr is not None and not _valid_cron(cron_expr):
        raise HTTPException(
            status_code=400, detail=f"invalid cron expression: {cron_expr!r}"
        )

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        source = session.get(IngestSource, source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="source not found")

        existing_job = (
            session.get(Job, source.job_id) if source.job_id is not None else None
        )

        if cron_expr is None:
            # Unschedule: delete the existing Job; keep the source.
            if existing_job is not None:
                session.delete(existing_job)
            source.job_id = None
            source.updated_at = now
            session.commit()
            return {"ok": True, "job_id": None, "cron_expr": None}

        job_config = json.dumps(
            {"source_id": int(source_id), "mapping_index": 0}
        )
        if existing_job is not None:
            existing_job.cron_expr = cron_expr
            existing_job.kind = "ingest_pull"
            existing_job.config = job_config
            existing_job.updated_at = now
            session.commit()
            return {
                "ok": True,
                "job_id": int(existing_job.id),
                "cron_expr": cron_expr,
            }

        job = Job(
            workspace_id=workspace_id,
            name=f"ingest:{source.name}",
            cron_expr=cron_expr,
            run_as_user_id=int(user["id"]),
            kind="ingest_pull",
            config=job_config,
            is_paused=False,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        source.job_id = int(job.id)
        source.updated_at = now
        session.commit()
        return {"ok": True, "job_id": int(job.id), "cron_expr": cron_expr}
