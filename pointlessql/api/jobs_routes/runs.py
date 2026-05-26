"""Run + task introspection endpoints.

* ``GET /api/jobs/{id}/tasks`` — task spec list.
* ``GET /api/jobs/{id}/runs`` — recent run rows.
* ``GET /api/jobs/{id}/runs/{run_id}/tasks`` — task-run rows for a
  specific run.
* ``GET /api/jobs/{id}/runs/{run_id}/logs`` — log lines.

All five short-circuit through :func:`load_job_or_404` so visibility
stays consistent with the CRUD endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.jobs_routes._access import load_job_or_404
from pointlessql.api.jobs_routes._serializers import (
    serialize_run,
    serialize_task,
    serialize_task_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs/{job_id}/tasks")
async def api_list_job_tasks(request: Request, job_id: int) -> list[dict[str, Any]]:
    """Return the :class:`JobTask` DAG nodes for *job_id*.

    Routes through :func:`load_job_or_404` first so non-admins
    cannot enumerate the DAG of a job they could not have
    triggered themselves.  The list is ordered by primary key so
    the DAG renders in insertion order even when ``order`` is
    ignored by the walker.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobTask as JobTaskModel

    load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [serialize_task(r) for r in rows]


@router.get("/api/jobs/{job_id}/runs")
async def api_list_job_runs(
    request: Request,
    job_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most-recent :class:`JobRun` rows for *job_id*.

    Newest-first ordering rides the
    ``(job_id, started_at DESC)`` index declared on
    :class:`~pointlessql.models.JobRun`. The default cap of 50 keeps
    the response payload small for the notebook-jobs panel
    while still surfacing enough history for a quick scan; deeper
    paging would land in a follow-up if needed.

    Args:
        request: Incoming FastAPI request — gated via
            :func:`load_job_or_404` so non-owners get a 404.
        job_id: Target job id.
        limit: Optional row cap, clamped to ``[1, 200]``.

    Returns:
        Serialised run rows, newest first.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    load_job_or_404(request, job_id)
    limit = max(1, min(int(limit), 200))
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(JobRunModel)
            .where(JobRunModel.job_id == job_id)
            .order_by(JobRunModel.started_at.desc())
            .limit(limit)
        )
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [serialize_run(r) for r in rows]


@router.get("/api/jobs/{job_id}/runs/{run_id}/tasks")
async def api_list_task_runs(request: Request, job_id: int, run_id: int) -> list[dict[str, Any]]:
    """Return per-task state rows for one :class:`JobRun`.

    The route gates on the parent job (via
    :func:`load_job_or_404`), then filters task runs by
    ``job_run_id`` so a caller can never read another job's task
    state by guessing a *run_id*.  Ordered by primary key so the
    DAG view stays stable across renders.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import TaskRun as TaskRunModel

    load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(TaskRunModel).where(TaskRunModel.job_run_id == run_id).order_by(TaskRunModel.id)
        )
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [serialize_task_run(r) for r in rows]


@router.get("/api/jobs/{job_id}/runs/{run_id}/logs")
async def api_list_job_logs(
    request: Request,
    job_id: int,
    run_id: int,
    task_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return log lines for one :class:`JobRun`, optionally filtered by task.

    The log panel on the job detail page fetches this endpoint via
    Alpine.js when the user expands a row; ``task_id`` lets the panel
    scope the view to one DAG node.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobLog as JobLogModel

    load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobLogModel).where(JobLogModel.job_run_id == run_id)
        if task_id is not None:
            stmt = stmt.where(JobLogModel.task_id == task_id)
        stmt = stmt.order_by(JobLogModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [
        {
            "id": r.id,
            "job_run_id": r.job_run_id,
            "task_id": r.task_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "level": r.level,
            "message": r.message,
        }
        for r in rows
    ]
