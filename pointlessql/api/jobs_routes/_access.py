"""Visibility + ownership helpers for jobs routes.

Both visibility rules match the docstring on
:func:`pointlessql.api.jobs_routes.api_list_jobs`: admins see every
job, non-admins see only jobs whose ``run_as_user_id`` matches their
user id.  Helpers raise the appropriate exception so the centralised
error handler renders a consistent response.

``JOB_REGISTRY`` is the eagerly-built scheduler registry; it's a
module-level constant so the kind / config validators in
:mod:`.crud` can sanity-check payloads without an extra DI round.
Re-exported from the package ``__init__`` for
:mod:`pointlessql.api.dashboards_routes` and
:mod:`pointlessql.api.notebooks_routes.jobs`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import get_user
from pointlessql.config import Settings
from pointlessql.exceptions import AuthorizationError
from pointlessql.services import scheduler as scheduler_service

JOB_REGISTRY = scheduler_service.build_default_registry()


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
    """Raise :class:`AuthorizationError` if the user can't mutate *job*.

    Admins always pass; otherwise the caller's user id must match
    ``job.run_as_user_id`` — the field the scheduler uses to build
    the per-run X-Principal header.  This keeps job-mutating routes
    aligned with run-time identity so a user can never edit a job
    that runs as someone else.
    """
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
