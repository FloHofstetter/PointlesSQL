"""Jobs + scheduler routes — CRUD, runs, tasks, logs, papermill artefacts.

Owns the full job-scheduler surface in one module:

* JSON CRUD: ``GET /api/jobs``, ``POST /api/jobs``,
  ``POST /api/jobs/{id}/run``, ``POST /api/jobs/{id}/pause``,
  ``POST /api/jobs/{id}/unpause``.
* Run/task introspection: ``GET /api/jobs/{id}/tasks``,
  ``GET /api/jobs/{id}/runs/{run_id}/tasks``,
  ``GET /api/jobs/{id}/runs/{run_id}/logs``.
* Papermill artefact serving:
  ``GET /jobs/{id}/runs/{run_id}/notebook`` (inline render),
  ``GET /jobs/{id}/runs/{run_id}/notebook/download`` (file),
  ``GET /jobs/{id}/runs/{run_id}/compare`` (side-by-side).
* HTML pages: ``GET /jobs`` (list), ``GET /jobs/{id}`` (detail).

Visibility model is unchanged from the pre-split shape: admin sees
every job; non-admin sees only jobs whose ``run_as_user_id`` matches
their user id.  Mutations (run / pause / unpause / create) check
admin-or-owner.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.exceptions import AuthorizationError
from pointlessql.services import notebook_render as notebook_render_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])

JOB_REGISTRY = scheduler_service.build_default_registry()


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


# -- Serializers ---------------------------------------------------------


def serialize_job(job: Any, last_run: Any = None) -> dict[str, Any]:
    """Render a :class:`Job` ORM row for JSON responses.

    Pulled out into a helper so both the list and the detail route
    emit the same shape; the helper assumes the ORM row has been
    detached from its session or the caller still holds the session
    open (we never serialize half-loaded jobs).

    When *last_run* is supplied (typically from
    :func:`latest_run_per_job`), the ``last_run_*`` fields are
    populated from it; otherwise they are ``None``. List endpoints
    thread the latest-run map in, detail/mutation endpoints do not —
    the keys are always present so clients never need to branch on
    their existence.

    Args:
        job: Detached :class:`~pointlessql.models.Job` ORM row.
        last_run: Optional latest :class:`~pointlessql.models.JobRun`
            for this job, used to populate ``last_run_*`` fields.

    Returns:
        A dict with the canonical job shape plus ``last_run_status``,
        ``last_run_at``, and ``last_run_duration_s``.
    """
    last_status: str | None = None
    last_at: str | None = None
    last_duration: float | None = None
    if last_run is not None:
        last_status = last_run.status
        last_at = last_run.started_at.isoformat() if last_run.started_at else None
        if last_run.started_at and last_run.finished_at:
            last_duration = (last_run.finished_at - last_run.started_at).total_seconds()
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "run_as_user_id": job.run_as_user_id,
        "kind": job.kind,
        "config": json.loads(job.config or "{}"),
        "is_paused": job.is_paused,
        "max_parallel_runs": job.max_parallel_runs,
        "on_failure_url": job.on_failure_url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "last_run_status": last_status,
        "last_run_at": last_at,
        "last_run_duration_s": last_duration,
    }


def latest_run_per_job(session: Any, job_ids: list[int]) -> dict[int, Any]:
    """Fetch the most recent :class:`JobRun` row for each of *job_ids*.

    One round-trip: a ``group_by(job_id)`` subquery pulls the max
    ``started_at`` per job, then the outer select joins back to
    ``job_runs`` on both columns to grab the full row. Portable
    across SQLite and Postgres — no window functions, no lateral
    joins — and rides the existing ``(job_id, started_at)`` index
    declared on :class:`~pointlessql.models.JobRun`.

    Args:
        session: An open SQLAlchemy session.
        job_ids: The jobs whose latest run should be fetched. May be
            empty, in which case an empty dict is returned without
            issuing a query.

    Returns:
        A mapping from ``job_id`` to its most recent
        :class:`~pointlessql.models.JobRun`. Jobs with no runs yet are
        simply absent from the dict.
    """
    if not job_ids:
        return {}
    from sqlalchemy import and_, func
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    latest_sq = (
        _select(
            JobRunModel.job_id.label("job_id"),
            func.max(JobRunModel.started_at).label("last_at"),
        )
        .where(JobRunModel.job_id.in_(job_ids))
        .group_by(JobRunModel.job_id)
        .subquery()
    )
    stmt = _select(JobRunModel).join(
        latest_sq,
        and_(
            JobRunModel.job_id == latest_sq.c.job_id,
            JobRunModel.started_at == latest_sq.c.last_at,
        ),
    )
    out: dict[int, Any] = {}
    for run in session.scalars(stmt).all():
        # Two runs with identical started_at timestamps would both
        # satisfy the join; pick the higher-id one so a single row
        # wins deterministically.
        prev = out.get(run.job_id)
        if prev is None or run.id > prev.id:
            out[run.job_id] = run
    for run in out.values():
        session.expunge(run)
    return out


def serialize_task(task: Any) -> dict[str, Any]:
    """Render a :class:`JobTask` ORM row for JSON responses."""
    return {
        "id": task.id,
        "job_id": task.job_id,
        "name": task.name,
        "kind": task.kind,
        "config": json.loads(task.config or "{}"),
        "depends_on": json.loads(task.depends_on or "[]"),
        "max_retries": task.max_retries,
        "retry_backoff_seconds": task.retry_backoff_seconds,
    }


def serialize_task_run(tr: Any) -> dict[str, Any]:
    """Render a :class:`TaskRun` ORM row for JSON responses."""
    return {
        "id": tr.id,
        "job_run_id": tr.job_run_id,
        "task_id": tr.task_id,
        "status": tr.status,
        "started_at": tr.started_at.isoformat() if tr.started_at else None,
        "finished_at": tr.finished_at.isoformat() if tr.finished_at else None,
        "attempts": tr.attempts,
        "error": tr.error,
    }


def serialize_run(run: Any) -> dict[str, Any]:
    """Render a :class:`JobRun` ORM row for JSON responses."""
    duration: float | None = None
    if run.started_at and run.finished_at:
        duration = (run.finished_at - run.started_at).total_seconds()
    return {
        "id": run.id,
        "job_id": run.job_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "trigger": run.trigger,
        "error": run.error,
        "duration_seconds": duration,
    }


def load_job_or_404(request: Request, job_id: int) -> Any:
    """Fetch a :class:`Job` with ownership-aware visibility rules.

    Admins see every job; non-admins see only jobs whose
    ``run_as_user_id`` matches their user id. A missing or hidden job
    surfaces as :class:`CatalogNotFoundError` so the centralized
    error handler renders 404 consistently.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Job as JobModel

    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        job = session.get(JobModel, job_id)
        if job is None:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        if not user.get("is_admin") and job.run_as_user_id != user["id"]:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        session.expunge(job)
        return job


def require_job_owner_or_admin(request: Request, job: Any) -> None:
    """Raise :class:`AuthorizationError` if the user can't mutate *job*."""
    user = get_user(request)
    if user.get("is_admin"):
        return
    if job.run_as_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="manage",
        securable_type="job",
        full_name=str(job.name),
    )


def load_papermill_run_output_path(request: Request, job_id: int, run_id: int) -> Path:
    """Validate *run_id* belongs to papermill *job_id* and return its runs dir.

    Shared validator for the inline render route and the download route.
    Both need the same three checks: caller can see the job, the job is a
    papermill job, and *run_id* really belongs to *job_id*.

    Args:
        request: Incoming FastAPI request; visibility is enforced via
            :func:`load_job_or_404`.
        job_id: The :class:`Job` id from the URL path.
        run_id: The :class:`JobRun` id from the URL path.

    Returns:
        The absolute ``runs/`` directory where ``{run_id}.ipynb`` lives.

    Raises:
        CatalogNotFoundError: If the job is not visible to the caller,
            the run does not belong to the job, or the job is not a
            papermill kind.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        run = session.get(JobRunModel, run_id)
        if run is None or run.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
    settings: Settings = request.app.state.settings
    return settings.jupyter.runs_dir.resolve()


# -- Routes --------------------------------------------------------------


@router.get("/api/jobs")
async def api_list_jobs(request: Request) -> list[dict[str, Any]]:
    """Return jobs visible to the current user.

    Admin sees everything; a regular user only sees jobs whose
    ``run_as_user_id`` matches their user id, matching the detail-page
    visibility so the two surfaces cannot drift.
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
    return [serialize_job(r, last_run=latest.get(r.id)) for r in rows]


@router.post("/api/jobs")
async def api_create_job(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new job (admin-only).

    Two shapes are accepted:

    * Single-task (legacy shape):
      ``{name, cron_expr, kind, config, ...}`` — the scheduler walks
      ``job.kind`` / ``job.config`` directly.
    * DAG:
      ``{name, cron_expr, tasks: [{name, kind, config, depends_on?,
      max_retries?, retry_backoff_seconds?}, ...], max_parallel_runs?}``.
      ``depends_on`` inside the payload references *task names* because
      the ids do not exist yet; the route resolves them to integer ids
      during insert and also validates the resulting graph is acyclic
      via :func:`pointlessql.services.scheduler.validate_dag` before
      committing so a bad payload never lands in the DB.

    ``run_as_user_id`` defaults to the caller so an admin scheduling a
    job for themselves does not have to look up their own id.
    """
    from croniter import croniter as _croniter

    from pointlessql.exceptions import ValidationError as _VE
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobTask as JobTaskModel

    require_admin(request)
    user = get_user(request)

    name = body.get("name")
    cron_expr = body.get("cron_expr")
    if not name or not cron_expr:
        raise _VE("name and cron_expr are required")
    if not _croniter.is_valid(str(cron_expr)):
        raise _VE(f"Invalid cron expression: {cron_expr!r}")

    tasks_payload = body.get("tasks")
    if tasks_payload is not None and not isinstance(tasks_payload, list):
        raise _VE("tasks must be a JSON array when provided")

    # Single-task shortcut: validate kind + config inline.
    if not tasks_payload:
        kind = body.get("kind")
        if not kind:
            raise _VE("kind is required when 'tasks' is not provided")
        JOB_REGISTRY.get(str(kind))
        config = body.get("config") or {}
        if not isinstance(config, dict):
            raise _VE("config must be a JSON object")
    else:
        kind = body.get("kind") or "python"  # placeholder on the Job row
        config = {}
        # Pre-flight each task entry so we fail fast before any INSERT.
        task_names: set[str] = set()
        for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(entry, dict):
                raise _VE("each task must be a JSON object")
            t_entry: dict[str, Any] = entry
            t_name = t_entry.get("name")
            t_kind = t_entry.get("kind")
            if not t_name or not t_kind:
                raise _VE("each task requires name and kind")
            if t_name in task_names:
                raise _VE(f"duplicate task name: {t_name!r}")
            task_names.add(str(t_name))
            JOB_REGISTRY.get(str(t_kind))
            t_config = t_entry.get("config") or {}
            if not isinstance(t_config, dict):
                raise _VE(f"task {t_name!r}: config must be a JSON object")
            t_deps = t_entry.get("depends_on") or []
            if not isinstance(t_deps, list):
                raise _VE(f"task {t_name!r}: depends_on must be a JSON array")

    run_as_user_id = int(body.get("run_as_user_id") or user["id"])
    is_paused = bool(body.get("is_paused", False))
    max_parallel_runs = int(body.get("max_parallel_runs") or 1)
    if max_parallel_runs < 1:
        raise _VE("max_parallel_runs must be >= 1")
    on_failure_url_raw = body.get("on_failure_url")
    on_failure_url: str | None = None
    if on_failure_url_raw is not None:
        if not isinstance(on_failure_url_raw, str) or not on_failure_url_raw.strip():
            raise _VE("on_failure_url must be a non-empty string when provided")
        on_failure_url = on_failure_url_raw.strip()

    now = datetime.now(UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        job = JobModel(
            name=str(name),
            cron_expr=str(cron_expr),
            run_as_user_id=run_as_user_id,
            kind=str(kind),
            config=json.dumps(config),
            is_paused=is_paused,
            max_parallel_runs=max_parallel_runs,
            on_failure_url=on_failure_url,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        # Flush-only, not commit: if DAG validation below fails, the
        # ``with factory() as session:`` context closes without commit
        # and the job row never lands in the DB (BUG-23-02).
        session.flush()

        if tasks_payload:
            # First pass: insert rows without depends_on so we learn ids.
            by_name: dict[str, JobTaskModel] = {}
            for order, entry in enumerate(tasks_payload):  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry: dict[str, Any] = entry
                jt = JobTaskModel(
                    job_id=job.id,
                    name=str(t_entry["name"]),
                    order=order,
                    kind=str(t_entry["kind"]),
                    config=json.dumps(t_entry.get("config") or {}),
                    depends_on="[]",
                    max_retries=int(t_entry.get("max_retries") or 0),
                    retry_backoff_seconds=int(t_entry.get("retry_backoff_seconds") or 0),
                )
                session.add(jt)
                session.flush()
                by_name[str(t_entry["name"])] = jt

            # Second pass: resolve depends_on names to ids.
            for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry = entry
                t_name = str(t_entry["name"])
                deps_names = t_entry.get("depends_on") or []
                resolved: list[int] = []
                for dn in deps_names:  # pyright: ignore[reportUnknownVariableType]
                    if dn not in by_name:
                        raise _VE(f"task {t_name!r} depends on unknown task {dn!r}")
                    resolved.append(by_name[str(dn)].id)
                by_name[t_name].depends_on = json.dumps(resolved)

            # Validate the resulting graph is acyclic BEFORE committing
            # so a failed validation leaves no job or task rows behind.
            scheduler_service.validate_dag(list(by_name.values()))

        # All validation passed — commit job + tasks atomically.
        session.commit()
        session.refresh(job)
        session.expunge(job)
    await audit(request, "create_job", f"job:{name}", json.dumps(body))
    return serialize_job(job)


@router.post("/api/jobs/{job_id}/run")
async def api_run_job(request: Request, job_id: int) -> dict[str, Any]:
    """Manually trigger a run of *job_id* (admin or owner only)."""
    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(factory, settings, JOB_REGISTRY, job_id, "manual")
    await audit(request, "run_job", f"job:{job.name}")
    return serialize_run(run)


@router.get("/api/jobs/{job_id}/tasks")
async def api_list_job_tasks(request: Request, job_id: int) -> list[dict[str, Any]]:
    """Return the :class:`JobTask` DAG nodes for *job_id*."""
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


@router.get("/api/jobs/{job_id}/runs/{run_id}/tasks")
async def api_list_task_runs(request: Request, job_id: int, run_id: int) -> list[dict[str, Any]]:
    """Return per-task state rows for one :class:`JobRun`."""
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


@router.get("/jobs/{job_id}/runs/{run_id}/notebook", response_class=HTMLResponse)
async def job_run_notebook(
    request: Request,
    job_id: int,
    run_id: int,
    exclude_input: bool = False,
) -> HTMLResponse:
    """Render an executed Papermill notebook inline.

    Returns the nbconvert ``lab``-template HTML body for
    ``{notebooks_dir}/runs/{run_id}.ipynb``. The job-detail page embeds
    this route in an iframe inside the "Output artifacts" card. A
    ``runs/{run_id}.html`` sidecar is written on first render so
    subsequent hits skip the nbconvert cost.

    When ``exclude_input=true`` is passed as a query param, the render
    hides code cells and caches to a sibling ``{run_id}.dashboard.html``
    sidecar — used by the dashboard iframe to publish output-only
    views of the latest succeeded run.
    """
    runs_dir = load_papermill_run_output_path(request, job_id, run_id)
    html = notebook_render_service.render_run_notebook(
        runs_dir,
        run_id,
        exclude_input=exclude_input,
    )
    return HTMLResponse(html)


@router.get("/jobs/{job_id}/runs/{run_id}/notebook/download")
async def job_run_notebook_download(
    request: Request,
    job_id: int,
    run_id: int,
    format: Literal["ipynb", "html"] = "ipynb",
) -> FileResponse:
    """Download the raw ipynb or cached-HTML sidecar for a run.

    A visibility-checked route is preferred over a StaticFiles mount
    so non-owner logged-in users cannot guess ``run_id`` values and
    exfiltrate another user's job output.  ``format=html`` triggers a
    render if the sidecar is not yet present.
    """
    from pointlessql.exceptions import CatalogNotFoundError

    runs_dir = load_papermill_run_output_path(request, job_id, run_id)
    if format == "html":
        # Ensure the sidecar exists before serving it.
        notebook_render_service.render_run_notebook(runs_dir, run_id)
        path = runs_dir / f"{run_id}.html"
        media_type = "text/html"
    else:
        path = runs_dir / f"{run_id}.ipynb"
        media_type = "application/x-ipynb+json"
    if not path.is_file():
        raise CatalogNotFoundError(f"Run {run_id} {format} artifact not found")
    return FileResponse(
        path,
        filename=f"job{job_id}_run{run_id}.{format}",
        media_type=media_type,
    )


@router.get("/jobs/{job_id}/runs/{run_id}/compare", response_class=HTMLResponse)
async def job_run_compare(
    request: Request,
    job_id: int,
    run_id: int,
    to: int,
) -> HTMLResponse:
    """Render two executed notebooks side-by-side for the same papermill job.

    Both runs must belong to ``job_id`` — this prevents leaking a peek
    at a different job's output by smuggling a foreign ``to=`` run id
    through the query string.  The page itself embeds two
    ``/jobs/{id}/runs/{rid}/notebook`` iframes; no cell-level diffing
    yet (a future enhancement if demand emerges).
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        left = session.get(JobRunModel, run_id)
        right = session.get(JobRunModel, to)
        if left is None or left.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
        if right is None or right.job_id != job_id:
            raise CatalogNotFoundError(f"Run {to} not found for job {job_id}")
        session.expunge(left)
        session.expunge(right)
    return _templates(request).TemplateResponse(
        request,
        "pages/run_compare.html",
        {
            "job": serialize_job(job),
            "left": serialize_run(left),
            "right": serialize_run(right),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.post("/api/jobs/{job_id}/pause")
async def api_pause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Pause *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = True
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "pause_job", f"job:{row.name}")
    return serialize_job(row)


@router.post("/api/jobs/{job_id}/unpause")
async def api_unpause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Resume *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = False
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "unpause_job", f"job:{row.name}")
    return serialize_job(row)


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_index(request: Request) -> HTMLResponse:
    """List every job visible to the current user."""
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
    return _templates(request).TemplateResponse(
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
    """Render job detail with task list, latest task statuses, and run history."""
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

    return _templates(request).TemplateResponse(
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
