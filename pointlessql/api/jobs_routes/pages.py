"""HTML pages for the jobs surface: list (``/jobs``) + detail (``/jobs/{id}``).

Both pages share the visibility model with the JSON CRUD endpoints
(admin sees all, non-admin sees own jobs) and reuse the serializers
to keep the first-paint payload identical to what the JSON twin
returns.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, get_user
from pointlessql.api.jobs_routes._access import (
    load_job_or_404,
)
from pointlessql.api.jobs_routes._serializers import (
    latest_run_per_job,
    serialize_job,
    serialize_run,
    serialize_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_index(request: Request) -> HTMLResponse:
    """List every job visible to the current user.

    Visibility mirrors :func:`load_job_or_404`: admins see every
    job, others see only jobs whose ``run_as_user_id`` matches
    them.  The latest run per job is fetched via
    :func:`latest_run_per_job` in a single query so the page does
    not fan out to one round-trip per row.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    jobs_data = [serialize_job(r, last_run=latest.get(r.id)) for r in rows]
    return get_templates(request).TemplateResponse(
        request,
        "pages/jobs.html",
        {
            "jobs": jobs_data,
            "is_admin": user.get("is_admin", False),
            "current_user_id": user.get("id"),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int) -> HTMLResponse:
    """Render job detail with task list, latest task statuses, and run history.

    Visibility goes through :func:`load_job_or_404` so non-owners
    get a 404 rather than an authorization error (no information
    leak about whether the id exists).  The run-history pane caps
    at the 20 most-recent runs to keep the page snappy on long-
    running jobs; deeper history is reachable through the
    ``/api/jobs/{id}/runs`` JSON endpoint.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel
    from pointlessql.models import JobTask as JobTaskModel
    from pointlessql.models import TaskRun as TaskRunModel

    job = load_job_or_404(request, job_id)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        runs_stmt = (
            _select(JobRunModel)
            .where(JobRunModel.job_id == job_id)
            .order_by(JobRunModel.started_at.desc())
            .limit(20)
        )
        runs = list(session.scalars(runs_stmt).all())
        for r in runs:
            session.expunge(r)

        tasks_stmt = (
            _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        )
        tasks = list(session.scalars(tasks_stmt).all())
        for t in tasks:
            session.expunge(t)

        # Fetch the latest :class:`TaskRun` per task so the table can
        # show current status + retry count without a second round-trip.
        latest_task_runs: dict[int, Any] = {}
        if runs and tasks:
            latest_run_id = runs[0].id
            tr_stmt = _select(TaskRunModel).where(TaskRunModel.job_run_id == latest_run_id)
            for tr in session.scalars(tr_stmt).all():
                session.expunge(tr)
                latest_task_runs[tr.task_id] = tr

    can_manage = user.get("is_admin", False) or job.run_as_user_id == user.get("id")

    task_rows: list[dict[str, Any]] = []
    for t in tasks:
        tr = latest_task_runs.get(t.id)
        task_rows.append(
            {
                **serialize_task(t),
                "latest_status": tr.status if tr is not None else None,
                "latest_attempts": tr.attempts if tr is not None else 0,
                "latest_error": tr.error if tr is not None else None,
                "latest_run_id": tr.job_run_id if tr is not None else None,
            },
        )

    return get_templates(request).TemplateResponse(
        request,
        "pages/job_detail.html",
        {
            "job": serialize_job(job),
            "runs": [serialize_run(r) for r in runs],
            "tasks": task_rows,
            "can_manage": can_manage,
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
