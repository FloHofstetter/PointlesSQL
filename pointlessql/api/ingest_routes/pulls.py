"""Phase 82.3 — manual pull + run-history endpoints.

* ``POST /api/ingest/sources/{id}/pulls`` — runs the configured
  reader synchronously for one (or every) mapping and returns the
  resulting stats.  Bypasses the scheduler so the "Pull now" button
  works even without a cron schedule.
* ``GET /api/ingest/sources/{id}/runs`` — returns the most recent
  pull stats per mapping (read from the source's ``table_mappings``
  JSON) plus the latest scheduled-run snapshot from ``job_runs``.

Manual pulls and scheduled pulls share the same executor body via
:func:`pointlessql.services.ingest.executor.run_pull`, so the audit
trail + fanout event behave identically.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models import IngestSource, JobRun
from pointlessql.services.ingest.executor import run_pull
from pointlessql.services.ingest.pull import PullError, load_mappings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest", "pulls"])


@router.post("/api/ingest/sources/{source_id}/pulls")
async def api_pull_now(
    request: Request,
    source_id: int,
    body: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Trigger one or every mapping pull synchronously.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.
        body: ``{"mapping_index": int | None}``.  When omitted or
            ``None`` every active mapping runs.

    Returns:
        ``{"ok": True, "results": [...], "failures": [...]}`` — both
        lists are populated so the caller sees per-mapping outcomes
        even when some succeed and some fail.

    Raises:
        ResourceNotFoundError: When the source doesn't exist.
        ValidationError: When ``mapping_index`` is out of range.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")
        if not row.is_active:
            raise ValidationError("source is paused; cannot pull.")
        mappings = load_mappings(row.table_mappings)
        if not mappings:
            raise ValidationError(
                "no table_mappings configured for this source.",
            )

    body_idx = body.get("mapping_index")
    if body_idx is not None:
        if not isinstance(body_idx, int) or not 0 <= body_idx < len(mappings):
            raise ValidationError(
                f"mapping_index out of range (0..{len(mappings) - 1}).",
            )
        targets = [body_idx]
    else:
        targets = list(range(len(mappings)))

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for idx in targets:
        try:
            outcome = await run_pull(
                source_id=source_id,
                mapping_index=idx,
                user_email=user.get("email") or "",
                job_run_id=0,  # 0 = manual pull marker; no JobRun row
                session_factory=factory,
            )
            results.append({"mapping_index": idx, **outcome})
        except PullError as exc:
            failures.append(
                {
                    "mapping_index": idx,
                    "reason": exc.reason,
                    "hint": exc.hint,
                }
            )
        except Exception as exc:  # noqa: BLE001 — log + surface
            logger.exception("manual pull crashed for source %s", source_id)
            failures.append(
                {
                    "mapping_index": idx,
                    "reason": f"Unexpected error: {type(exc).__name__}",
                    "hint": "See server logs.",
                }
            )

    return {"ok": True, "results": results, "failures": failures}


@router.get("/api/ingest/sources/{source_id}/runs")
async def api_list_source_runs(
    request: Request,
    source_id: int,
    limit: int = 20,
) -> dict[str, Any]:
    """List recent pull executions for a source.

    Composite view: the latest ``last_pull_stats`` per mapping (covers
    both manual and last-scheduled run) plus the scheduled-run history
    pulled from ``job_runs`` linked to the source's ``job_id``.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.
        limit: Cap on the JobRun history slice.

    Returns:
        ``{"latest_per_mapping": [...], "scheduled_history": [...]}``.

    Raises:
        ResourceNotFoundError: When the source doesn't exist.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError("source not found")

        try:
            mappings = json.loads(row.table_mappings or "[]")
        except (ValueError, TypeError):
            mappings = []
        latest: list[dict[str, Any]] = []
        if isinstance(mappings, list):
            for idx, m in enumerate(mappings):  # type: ignore[reportUnknownVariableType]
                if not isinstance(m, dict):
                    continue
                stats = m.get("last_pull_stats")  # type: ignore[reportUnknownMemberType]
                if not isinstance(stats, dict):
                    continue
                latest.append(
                    {
                        "mapping_index": idx,
                        "source_table": m.get("source_table"),  # type: ignore[reportUnknownArgumentType]
                        "target_fqn": m.get("target_fqn"),  # type: ignore[reportUnknownArgumentType]
                        "stats": stats,
                    }
                )

        scheduled: list[dict[str, Any]] = []
        if row.job_id is not None:
            stmt = (
                select(JobRun)
                .where(JobRun.job_id == row.job_id)
                .order_by(JobRun.started_at.desc())
                .limit(int(limit))
            )
            for jr in session.scalars(stmt).all():
                scheduled.append(
                    {
                        "id": int(jr.id),
                        "status": jr.status,
                        "trigger": jr.trigger,
                        "started_at": jr.started_at.isoformat()
                        if jr.started_at
                        else None,
                        "finished_at": jr.finished_at.isoformat()
                        if jr.finished_at
                        else None,
                        "error": jr.error,
                    }
                )

    return {"latest_per_mapping": latest, "scheduled_history": scheduled}
