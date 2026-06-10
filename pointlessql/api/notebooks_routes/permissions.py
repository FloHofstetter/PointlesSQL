"""Notebook permission CRUD routes.

Per-notebook share grants layered on top of workspace membership.
A row here grants access ``view`` / ``run`` / ``edit`` independent
of the workspace default permissioning, so a stakeholder can be
elevated on a single notebook without workspace-wide impact.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import get_optional_user, require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import permissions as notebook_perms_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    """Resolve a ``?path=`` query into the stable notebook UUID."""
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/permissions")
async def api_list_permissions(
    request: Request, path: str = Query(..., min_length=1)
) -> JSONResponse:
    """List explicit grants on a notebook.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path.

    Returns:
        JSON ``{path, notebook_id, permissions: [...], roles: [...]}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_perms_service.list_permissions(session, notebook_id=notebook_id)
    return JSONResponse(
        {
            "path": path,
            "notebook_id": notebook_id,
            "permissions": rows,
            "roles": list(notebook_perms_service.VALID_ROLES),
        }
    )


@router.put("/api/notebooks/permissions")
async def api_grant_permission(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Insert or update one ``(notebook, user)`` grant.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{path, user_id, role}``.

    Returns:
        JSON ``{user_id, role}``.

    Raises:
        ValidationError: On bad input shape.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    user_id_raw = body.get("user_id")
    role = body.get("role")
    if not isinstance(path, str):
        raise ValidationError("body.path must be a string")
    if not isinstance(user_id_raw, int):
        raise ValidationError("body.user_id must be an integer")
    if not isinstance(role, str):
        raise ValidationError("body.role must be a string")
    notebook_id = _resolve_notebook_uuid(request, path)
    actor = get_optional_user(request)
    actor_id: int | None = actor.get("id") if actor else None
    factory = request.app.state.session_factory
    with factory() as session:
        notebook_perms_service.grant_permission(
            session,
            notebook_id=notebook_id,
            user_id=user_id_raw,
            role=role,
            granted_by_user_id=actor_id,
        )
        session.commit()
    return JSONResponse({"user_id": user_id_raw, "role": role})


@router.delete("/api/notebooks/permissions")
async def api_revoke_permission(
    request: Request,
    path: str = Query(..., min_length=1),
    user_id: int = Query(...),
) -> JSONResponse:
    """Remove one grant; idempotent.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path.
        user_id: ``users.id`` of the grantee.

    Returns:
        JSON ``{removed: bool}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        removed = notebook_perms_service.revoke_permission(
            session, notebook_id=notebook_id, user_id=user_id
        )
        session.commit()
    return JSONResponse({"removed": removed})
