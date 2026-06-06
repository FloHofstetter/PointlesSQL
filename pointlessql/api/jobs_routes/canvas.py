"""Visual task-chain (DAG) canvas routes for a job.

Read-side adapters over :mod:`pointlessql.services.scheduler._canvas` that
let the shared Drawflow editor drive a job's task graph:

* ``GET  /api/jobs/{id}/canvas``             — snapshot the job's tasks as a
  ``CanvasDoc``.
* ``POST /api/jobs/{id}/canvas/validate``    — side-effect-free shape /
  cycle / kind / name checks.
* ``GET  /api/jobs/{id}/canvas/run-status``  — per-node ``TaskRun`` status
  overlay for one run.
* ``GET  /api/jobs/{id}/_kinds``             — the runnable task-kind palette
  fed from the executor registry.

The diff-save ``POST /api/jobs/{id}/canvas`` lands separately so the
read-only surface can ship first.  Every route enforces the same
ownership-aware visibility as the rest of the jobs API via
:func:`load_job_or_404`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from pointlessql.api.dependencies import require_user
from pointlessql.api.jobs_routes._access import (
    JOB_REGISTRY,
    load_job_or_404,
    require_job_owner_or_admin,
)
from pointlessql.services.canvas_core import CanvasDoc
from pointlessql.services.scheduler._canvas import (
    JobDagSaveSummary,
    apply_job_dag_doc,
    build_job_dag_doc,
    build_run_status,
    validate_job_dag_doc,
)

router = APIRouter(tags=["jobs-canvas"])


class JobCanvasLoadResponse(BaseModel):
    """Response for ``GET /api/jobs/{id}/canvas``."""

    document: CanvasDoc


class JobCanvasSaveRequest(BaseModel):
    """Body for ``POST /api/jobs/{id}/canvas``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc


class JobCanvasSaveResponse(BaseModel):
    """Response for ``POST /api/jobs/{id}/canvas``.

    Returns the freshly-rebuilt document so the editor can rewrite the
    optimistic ids it minted for new nodes (also surfaced as ``id_remap``).
    """

    summary: JobDagSaveSummary
    document: CanvasDoc


class JobCanvasValidateRequest(BaseModel):
    """Body for ``POST /api/jobs/{id}/canvas/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: CanvasDoc


class JobCanvasValidateResponse(BaseModel):
    """Response for ``POST /api/jobs/{id}/canvas/validate``."""

    issues: list[str]


class JobCanvasRunStatusResponse(BaseModel):
    """Response for ``GET /api/jobs/{id}/canvas/run-status``."""

    statuses: dict[str, str]


class JobKindEntry(BaseModel):
    """One runnable task kind for the editor palette."""

    type: str
    label: str


class JobKindsResponse(BaseModel):
    """Response for ``GET /api/jobs/{id}/_kinds``."""

    kinds: list[JobKindEntry]


def _kind_label(kind: str) -> str:
    """Humanize a registry kind id into a palette label."""
    return kind.replace("_", " ").title()


@router.get("/api/jobs/{job_id}/canvas", response_model=JobCanvasLoadResponse)
def get_job_canvas(job_id: int, request: Request) -> JobCanvasLoadResponse:
    """Snapshot a job's task graph as a ``CanvasDoc``."""
    require_user(request)
    load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    doc = build_job_dag_doc(factory, job_id=job_id)
    return JobCanvasLoadResponse(document=doc)


@router.post("/api/jobs/{job_id}/canvas", response_model=JobCanvasSaveResponse)
def save_job_canvas(
    job_id: int, body: JobCanvasSaveRequest, request: Request
) -> JobCanvasSaveResponse:
    """Diff *body.document* against the job's tasks and apply the delta.

    Requires job-owner / admin rights.  The whole save is one transaction
    gated by ``validate_dag`` before commit, so a cyclic edit rolls back; a
    task with an in-flight run cannot be deleted.
    """
    require_user(request)
    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    summary = apply_job_dag_doc(
        factory,
        job_id=job_id,
        doc=body.document,
        known_kinds=set(JOB_REGISTRY.kinds()),
    )
    fresh = build_job_dag_doc(factory, job_id=job_id)
    return JobCanvasSaveResponse(summary=summary, document=fresh)


@router.post(
    "/api/jobs/{job_id}/canvas/validate",
    response_model=JobCanvasValidateResponse,
)
def validate_job_canvas(
    job_id: int, body: JobCanvasValidateRequest, request: Request
) -> JobCanvasValidateResponse:
    """Run side-effect-free shape / cycle / kind / name checks."""
    require_user(request)
    load_job_or_404(request, job_id)
    issues = validate_job_dag_doc(
        body.document, known_kinds=set(JOB_REGISTRY.kinds())
    )
    return JobCanvasValidateResponse(issues=issues)


@router.get(
    "/api/jobs/{job_id}/canvas/run-status",
    response_model=JobCanvasRunStatusResponse,
)
def job_canvas_run_status(
    job_id: int, run_id: int, request: Request
) -> JobCanvasRunStatusResponse:
    """Overlay one run's per-task statuses onto the canvas node ids."""
    require_user(request)
    load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    statuses = build_run_status(factory, job_id=job_id, run_id=run_id)
    return JobCanvasRunStatusResponse(statuses=statuses)


@router.get("/api/jobs/{job_id}/_kinds", response_model=JobKindsResponse)
def job_canvas_kinds(job_id: int, request: Request) -> JobKindsResponse:
    """Return the runnable task-kind palette for the editor."""
    require_user(request)
    load_job_or_404(request, job_id)
    kinds = [
        JobKindEntry(type=k, label=_kind_label(k)) for k in JOB_REGISTRY.kinds()
    ]
    return JobKindsResponse(kinds=kinds)


__all__ = [
    "JobCanvasLoadResponse",
    "JobCanvasRunStatusResponse",
    "JobCanvasSaveRequest",
    "JobCanvasSaveResponse",
    "JobCanvasValidateRequest",
    "JobCanvasValidateResponse",
    "JobKindsResponse",
    "router",
]
