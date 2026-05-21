"""Notebook branch-binding routes (Phase 102)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import (
    branch_bindings as notebook_branch_bindings_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/branch")
async def api_get_current_branch_binding(
    request: Request, path: str = Query(..., min_length=1)
) -> JSONResponse:
    """Return the active branch binding for one notebook (or ``null``)."""
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_branch_bindings_service.get_current_binding(
            session, notebook_id=notebook_id
        )
    return JSONResponse(
        {
            "path": path,
            "notebook_id": notebook_id,
            "current": envelope,
        }
    )


@router.post("/api/notebooks/branch", status_code=201)
async def api_bind_branch(
    request: Request, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    """Set the current branch binding.

    Body keys:
        path: Relative notebook path.
        branch_name: Delta-branch name (validated).
        base_revision_uuid: Optional Phase-97 revision uuid.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    branch_name = body.get("branch_name")
    base_rev = body.get("base_revision_uuid")
    if not isinstance(path, str) or not isinstance(branch_name, str):
        raise ValidationError(
            "body.path and body.branch_name must be strings"
        )
    if base_rev is not None and not isinstance(base_rev, str):
        raise ValidationError("body.base_revision_uuid must be a string or null")
    notebook_id = _resolve_notebook_uuid(request, path)
    actor_id: int | None = None
    try:
        actor_id = (
            request.state.user.get("id") if request.state.user else None
        )
    except AttributeError:
        actor_id = None
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_branch_bindings_service.bind_branch(
            session,
            notebook_id=notebook_id,
            branch_name=branch_name,
            base_revision_uuid=base_rev,
            created_by_user_id=actor_id,
        )
        envelope = notebook_branch_bindings_service.binding_to_envelope(row)
        session.commit()
    return JSONResponse(envelope, status_code=201)


@router.post("/api/notebooks/branch/promote")
async def api_promote_branch(
    request: Request, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    """Mark the current branch binding as promoted (human-reviewed gate).

    Body keys:
        path: Relative notebook path.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    if not isinstance(path, str):
        raise ValidationError("body.path must be a string")
    notebook_id = _resolve_notebook_uuid(request, path)
    actor_id: int | None = None
    actor_email: str | None = None
    try:
        if request.state.user:
            actor_id = request.state.user.get("id")
            actor_email = request.state.user.get("email")
    except AttributeError:
        actor_id = None
        actor_email = None
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_branch_bindings_service.promote_binding(
            session,
            notebook_id=notebook_id,
            promoted_by_user_id=actor_id,
            promoted_by_user_email=actor_email,
        )
        envelope = notebook_branch_bindings_service.binding_to_envelope(row)
        session.commit()
    return JSONResponse(envelope)


@router.delete("/api/notebooks/branch")
async def api_discard_branch(
    request: Request, path: str = Query(..., min_length=1)
) -> JSONResponse:
    """Discard the current binding (roll back without promotion)."""
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_branch_bindings_service.discard_binding(
            session, notebook_id=notebook_id
        )
        envelope = (
            notebook_branch_bindings_service.binding_to_envelope(row) if row else None
        )
        session.commit()
    return JSONResponse({"discarded": envelope})


@router.get("/api/notebooks/branch/history")
async def api_list_branch_history(
    request: Request,
    path: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    """Return historical bindings, newest first."""
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_branch_bindings_service.list_bindings(
            session, notebook_id=notebook_id, limit=limit
        )
    return JSONResponse(
        {"path": path, "notebook_id": notebook_id, "bindings": rows}
    )
