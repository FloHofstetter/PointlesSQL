"""Notebook-job linkage + one-shot ``run-once`` trigger.

The two endpoints here bridge the notebook editor to the scheduler:

* ``GET  /api/notebooks/jobs`` — list scheduled jobs / recent runs
  for one notebook path.
* ``POST /api/notebooks/run-once`` — fire a single papermill run
  via a paused-job audit anchor (manual / fire-and-forget).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services import scheduler as scheduler_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/jobs")
async def api_notebook_jobs(
    request: Request,
    path: str,
    limit: int = 10,
) -> dict[str, Any]:
    """List scheduled jobs + recent runs for one notebook.

    Powers the Phase 67.4 in-editor side-panel that surfaces
    "what runs does this notebook have?" without making the user
    navigate to ``/jobs`` and filter manually. Joins
    :class:`NotebookJobLink` → :class:`Job` for the scheduled set,
    then pulls the most-recent :class:`JobRun` rows across all those
    jobs.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative notebook path the editor is open on.
        limit: Optional cap on the recent-runs list, clamped to
            ``[1, 50]``. Default 10 mirrors the panel design.

    Returns:
        A JSON dict ``{scheduled_jobs: [...], recent_runs: [...]}``.
        Each scheduled entry carries job_id + name + cron + paused
        flag + last_run_at/status; recent_runs are flat
        :class:`JobRun` summaries newest-first.

    Raises:
        ValidationError: When ``path`` is missing or non-string.
    """  # noqa: DOC502
    from sqlalchemy import select as _select

    from pointlessql.api.jobs_routes import serialize_job as _serialize_job
    from pointlessql.api.jobs_routes import serialize_run as _serialize_run
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel
    from pointlessql.models import NotebookJobLink as _NJL

    require_user(request)
    if not isinstance(path, str) or not path:
        raise ValidationError("`path` is required")
    limit = max(1, min(int(limit), 50))
    factory = request.app.state.session_factory
    with factory() as session:
        link_stmt = _select(_NJL).where(_NJL.notebook_path == path)
        link_rows = list(session.scalars(link_stmt).all())
        job_ids = [r.job_id for r in link_rows]
        scheduled: list[dict[str, Any]] = []
        recent: list[dict[str, Any]] = []
        if job_ids:
            jobs_stmt = _select(JobModel).where(JobModel.id.in_(job_ids))
            job_rows = list(session.scalars(jobs_stmt).all())
            for j in job_rows:
                session.expunge(j)
            # Last-run lookup per job (one round-trip via subquery).
            from pointlessql.api.jobs_routes import latest_run_per_job as _latest

            last_runs_map = _latest(session, [int(j.id) for j in job_rows])
            for j in job_rows:
                scheduled.append(_serialize_job(j, last_runs_map.get(int(j.id))))

            runs_stmt = (
                _select(JobRunModel)
                .where(JobRunModel.job_id.in_(job_ids))
                .order_by(JobRunModel.started_at.desc())
                .limit(limit)
            )
            run_rows = list(session.scalars(runs_stmt).all())
            for r in run_rows:
                session.expunge(r)
            recent = [_serialize_run(r) for r in run_rows]
    return {"scheduled_jobs": scheduled, "recent_runs": recent}


@router.post("/api/notebooks/run-once")
async def api_run_once(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Trigger a one-shot papermill run of a notebook.

    Creates a paused :class:`~pointlessql.models.Job` row carrying
    ``kind="papermill"`` + ``config={notebook_path, parameters}`` so
    the run lands in the same audit-trail surfaces as scheduled jobs.
    Immediately fires a manual run via
    :func:`scheduler_service.execute_run`, returned as a fire-and-
    forget :class:`asyncio.Task` — the HTTP response carries
    ``{job_id, job_run_id}`` so the browser can poll
    ``GET /api/jobs/{job_id}/runs`` until the run reaches a terminal
    status. The job stays paused after the run, so it never re-fires
    on a cron tick and stays around purely as an audit-trail anchor.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        body: JSON with keys ``path`` (relative notebook path) and
            optional ``parameters`` (dict of papermill overrides).

    Returns:
        JSON ``{"job_id": int, "job_run_id": int, "status": "started"}``.

    Raises:
        ValidationError: When ``path`` is missing / non-string,
            ``parameters`` is not a dict, or the path resolution
            (escape / suffix / existence) rejects the input.
    """  # noqa: DOC502
    import asyncio
    import json as _json
    from datetime import UTC, datetime

    from croniter import croniter as _croniter

    from pointlessql.api._audit_helpers import audit
    from pointlessql.api.dependencies import get_user
    from pointlessql.api.jobs_routes import JOB_REGISTRY
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel

    require_user(request)
    user = get_user(request)
    settings: Settings = request.app.state.settings

    path = body.get("path")
    if not isinstance(path, str) or not path:
        raise ValidationError("`path` is required")
    parameters = body.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValidationError("`parameters` must be a JSON object")

    # Path validation reuses the executor's resolver, which rejects
    # absolute paths, missing files, traversal, and bad suffixes.
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        path,
    )
    # Touch ``resolved`` to keep the lint happy + the import alive.
    _ = resolved

    # A cron expression we never want to re-fire on. ``is_paused=True``
    # already gates the scheduler, but pinning a far-future minute as a
    # second line of defence keeps the row inert if a future operator
    # ever unpauses it by accident.
    cron_expr = "0 0 1 1 *"
    if not _croniter.is_valid(cron_expr):
        # Should never happen — croniter accepts the canonical 5-field form.
        raise ValidationError("internal: cron sentinel rejected by croniter")

    stamp = datetime.now(UTC)
    safe_path = path.replace("/", "_").replace(".", "_")
    job_name = (
        f"notebook-runonce:{safe_path}:{user['id']}:"
        f"{stamp.strftime('%Y%m%d-%H%M%S-%f')}"
    )
    config_blob = _json.dumps(
        {"notebook_path": path, "parameters": parameters},
    )

    factory = request.app.state.session_factory
    with factory() as session:
        job = JobModel(
            name=job_name,
            cron_expr=cron_expr,
            run_as_user_id=int(user["id"]),
            kind="papermill",
            config=config_blob,
            is_paused=True,
            max_parallel_runs=1,
            on_failure_url=None,
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = int(job.id)
        # keeps run-once jobs visible in
        # the editor's notebook-jobs panel just like scheduled jobs.
        from pointlessql.models import NotebookJobLink as _NJL

        session.add(
            _NJL(
                workspace_id=1,
                notebook_path=path,
                job_id=job_id,
                created_at=stamp,
            ),
        )
        session.commit()
        # Pre-insert the JobRun row so the browser can poll immediately;
        # ``execute_run`` will update its status as the run progresses.
        # Actually, ``execute_run`` inserts its own JobRun — we just
        # capture the resulting run id by reading the latest row after
        # the task spawns. Re-read pattern matches ``api_run_job``.

    # Fire-and-forget — the HTTP response returns as soon as the task is
    # scheduled. The browser polls ``/api/jobs/{job_id}/runs`` for
    # status.
    asyncio.create_task(
        scheduler_service.execute_run(
            factory, settings, JOB_REGISTRY, job_id, "manual",
        ),
    )

    # Capture the freshly-created JobRun row id with a short retry —
    # ``execute_run`` inserts the row on entry, so a tiny grace gives
    # the task scheduler one tick to make it visible. Five retries with
    # 20 ms spacing is well under any user-perceptible delay.
    job_run_id: int | None = None
    for _ in range(5):
        with factory() as session:
            row = (
                session.query(JobRunModel)
                .filter(JobRunModel.job_id == job_id)
                .order_by(JobRunModel.id.desc())
                .first()
            )
            if row is not None:
                job_run_id = int(row.id)
                break
        await asyncio.sleep(0.02)

    await audit(request, "run_once_notebook", f"notebook:{path}")
    return JSONResponse(
        {
            "job_id": job_id,
            "job_run_id": job_run_id,
            "status": "started",
        },
    )
