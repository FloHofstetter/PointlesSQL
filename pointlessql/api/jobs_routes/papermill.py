"""Papermill artefact endpoints — inline render, download, compare.

These three HTML / file routes operate on the papermill kind only.
Visibility goes through :func:`load_papermill_run_output_path` which
enforces (a) caller can see the job, (b) job kind is ``papermill``,
(c) the requested run id belongs to the job.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from pointlessql.api.dependencies import get_templates
from pointlessql.api.jobs_routes._access import (
    load_job_or_404,
    load_papermill_run_output_path,
)
from pointlessql.api.jobs_routes._serializers import serialize_job, serialize_run
from pointlessql.services import notebook_render as notebook_render_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


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
    return get_templates(request).TemplateResponse(
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

