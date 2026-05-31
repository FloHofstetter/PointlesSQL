"""HTTP routes for the editable workspace-level mesh canvas.

Three thin adapters over :mod:`pointlessql.services.mesh._canvas`:

* ``GET    /api/mesh/canvas``           — load the workspace snapshot.
* ``POST   /api/mesh/canvas``           — save by diffing client edges
  against the current ``upstream_product`` port rows; new edges create
  one input port, removed edges delete one.
* ``POST   /api/mesh/canvas/validate``  — surface side-effect-free
  shape issues (self-loops, duplicate wires) without touching the DB.

Plus the HTML page handler at ``GET /mesh/canvas`` that renders the
standalone editor template.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.services.mesh._canvas import (
    MeshCanvasDoc,
    MeshDiffSummary,
    apply_mesh_canvas_doc,
    build_mesh_canvas_doc,
    validate_mesh_canvas_doc,
)
from pointlessql.types import UserInfo

router = APIRouter(prefix="/api/mesh", tags=["mesh-canvas"])
html_router = APIRouter(tags=["mesh-canvas-html"])


def _require_workspace_write(user: UserInfo) -> None:
    if not bool(user.get("is_admin")):
        raise AuthorizationError(
            principal=str(user.get("email", "")),
            privilege="mesh-canvas-write",
            securable_type="workspace",
            full_name="default",
        )


class MeshCanvasLoadResponse(BaseModel):
    """Response for ``GET /api/mesh/canvas``."""

    document: MeshCanvasDoc


class MeshCanvasSaveRequest(BaseModel):
    """Body for ``POST /api/mesh/canvas``."""

    model_config = ConfigDict(extra="forbid")

    document: MeshCanvasDoc


class MeshCanvasSaveResponse(BaseModel):
    """Response for ``POST /api/mesh/canvas``."""

    summary: MeshDiffSummary
    document: MeshCanvasDoc


class MeshCanvasValidateRequest(BaseModel):
    """Body for ``POST /api/mesh/canvas/validate``."""

    model_config = ConfigDict(extra="forbid")

    document: MeshCanvasDoc


class MeshCanvasValidateResponse(BaseModel):
    """Response for ``POST /api/mesh/canvas/validate``."""

    issues: list[str]


@router.get("/canvas", response_model=MeshCanvasLoadResponse)
def get_mesh_canvas(request: Request) -> MeshCanvasLoadResponse:
    """Snapshot the workspace's DPs + ``upstream_product`` bindings."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    doc = build_mesh_canvas_doc(factory, workspace_id=workspace_id)
    return MeshCanvasLoadResponse(document=doc)


@router.post("/canvas", response_model=MeshCanvasSaveResponse)
def save_mesh_canvas(
    body: MeshCanvasSaveRequest, request: Request
) -> MeshCanvasSaveResponse:
    """Diff *body.document* against the current state and apply the delta."""
    require_user(request)
    user = get_user(request)
    _require_workspace_write(user)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    actor_id = int(user["id"]) if user["id"] > 0 else None
    summary = apply_mesh_canvas_doc(
        factory,
        workspace_id=workspace_id,
        doc=body.document,
        actor_user_id=actor_id,
    )
    fresh = build_mesh_canvas_doc(factory, workspace_id=workspace_id)
    return MeshCanvasSaveResponse(summary=summary, document=fresh)


@router.post("/canvas/validate", response_model=MeshCanvasValidateResponse)
def validate_mesh_canvas(
    body: MeshCanvasValidateRequest, request: Request
) -> MeshCanvasValidateResponse:
    """Run side-effect-free shape checks on *body.document*."""
    require_user(request)
    issues = validate_mesh_canvas_doc(body.document)
    return MeshCanvasValidateResponse(issues=issues)


@html_router.get(
    "/mesh/canvas", response_class=HTMLResponse, response_model=None
)
def mesh_canvas_editor_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the standalone mesh-canvas editor template."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/mesh/canvas", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/mesh_canvas_editor.html",
        {
            "current_user_id": int(user.get("id") or 0),
            "is_admin": bool(user.get("is_admin")),
            "active_page": "mesh",
        },
    )


__all__ = [
    "MeshCanvasLoadResponse",
    "MeshCanvasSaveRequest",
    "MeshCanvasSaveResponse",
    "MeshCanvasValidateRequest",
    "MeshCanvasValidateResponse",
    "html_router",
    "router",
]
