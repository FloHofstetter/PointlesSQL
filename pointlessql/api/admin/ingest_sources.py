"""Phase 82.5 — system-wide ingest health monitor (admin-only).

* ``GET /api/admin/ingest-sources`` — list every IngestSource across
  workspaces with a rollup health summary (last pull status, last
  success ts, errors / rows over the last 7 days).
* ``GET /api/admin/ingest-sources/{id}/health`` — drilldown returning
  the last 30 ``job_runs`` for the source's Job + per-day rollup.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.dependencies import require_admin
from pointlessql.models import IngestSource, Job, JobRun

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "ingest-sources"])


def _source_summary(
    row: IngestSource,
    *,
    job: Job | None,
    runs_7d: list[JobRun],
) -> dict[str, Any]:
    """Project a source + its recent JobRuns into a rollup dict."""
    try:
        mappings_raw = json.loads(row.table_mappings or "[]")
    except (ValueError, TypeError):
        mappings_raw = []
    mappings: list[dict[str, Any]] = (
        [m for m in cast(list[Any], mappings_raw) if isinstance(m, dict)]
        if isinstance(mappings_raw, list)
        else []
    )
    last_stats: dict[str, Any] | None = None
    for m in mappings:
        stats_raw = m.get("last_pull_stats")
        if not isinstance(stats_raw, dict):
            continue
        stats = cast(dict[str, Any], stats_raw)
        if last_stats is None:
            last_stats = stats
            continue
        ts_a = str(stats.get("ts") or "")
        ts_b = str(last_stats.get("ts") or "")
        if ts_a > ts_b:
            last_stats = stats

    errors_7d = sum(1 for r in runs_7d if r.status == "failed")
    successes_7d = sum(1 for r in runs_7d if r.status == "succeeded")
    return {
        "id": int(row.id),
        "workspace_id": int(row.workspace_id),
        "name": row.name,
        "kind": row.kind,
        "is_active": bool(row.is_active),
        "mapping_count": len(mappings),
        "cron_expr": job.cron_expr if job is not None else None,
        "is_paused": bool(job.is_paused) if job is not None else None,
        "last_pull_ts": (last_stats or {}).get("ts"),
        "last_pull_ok": (
            bool((last_stats or {}).get("ok"))
            if last_stats is not None
            else None
        ),
        "last_pull_rows": (last_stats or {}).get("rows_written"),
        "errors_7d": errors_7d,
        "successes_7d": successes_7d,
    }


@router.get("/api/admin/ingest-sources")
async def api_admin_list_ingest_sources(request: Request) -> dict[str, Any]:
    """List every IngestSource with a rollup health row.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"sources": [{...}, ...]}`` ordered newest-first.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7)
    with factory() as session:
        rows = list(
            session.scalars(
                select(IngestSource).order_by(IngestSource.created_at.desc())
            ).all()
        )
        job_ids = [r.job_id for r in rows if r.job_id is not None]
        jobs_by_id: dict[int, Job] = {}
        if job_ids:
            jobs_by_id = {
                int(j.id): j
                for j in session.scalars(
                    select(Job).where(Job.id.in_(job_ids))
                ).all()
            }
        runs_by_job: dict[int, list[JobRun]] = {}
        if job_ids:
            for jr in session.scalars(
                select(JobRun).where(
                    JobRun.job_id.in_(job_ids),
                    JobRun.started_at >= cutoff,
                )
            ).all():
                runs_by_job.setdefault(int(jr.job_id), []).append(jr)
        out = [
            _source_summary(
                r,
                job=(jobs_by_id.get(r.job_id) if r.job_id is not None else None),
                runs_7d=(
                    runs_by_job.get(r.job_id, [])
                    if r.job_id is not None
                    else []
                ),
            )
            for r in rows
        ]
    return {"sources": out}


@router.get("/api/admin/ingest-sources/{source_id}/health")
async def api_admin_ingest_source_health(
    request: Request, source_id: int
) -> dict[str, Any]:
    """Per-source drilldown: last 30 JobRuns + per-day rollup.

    Args:
        request: Incoming FastAPI request.
        source_id: IngestSource primary key.

    Returns:
        ``{"source": {...}, "runs": [...], "per_day": [...]}``.

    Raises:
        HTTPException: 404 when the source doesn't exist.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None:
            raise HTTPException(status_code=404, detail="source not found")
        runs: list[JobRun] = []
        if row.job_id is not None:
            runs = list(
                session.scalars(
                    select(JobRun)
                    .where(JobRun.job_id == row.job_id)
                    .order_by(JobRun.started_at.desc())
                    .limit(30)
                ).all()
            )
        per_day: dict[str, dict[str, int]] = {}
        for jr in runs:
            day = jr.started_at.date().isoformat()
            slot = per_day.setdefault(day, {"succeeded": 0, "failed": 0})
            if jr.status == "succeeded":
                slot["succeeded"] += 1
            elif jr.status == "failed":
                slot["failed"] += 1
    return {
        "source": {
            "id": int(row.id),
            "workspace_id": int(row.workspace_id),
            "name": row.name,
            "kind": row.kind,
            "is_active": bool(row.is_active),
        },
        "runs": [
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
            for jr in runs
        ],
        "per_day": [
            {"day": day, **counts}
            for day, counts in sorted(per_day.items())
        ],
    }
