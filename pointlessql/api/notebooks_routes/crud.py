"""Notebook file CRUD on disk: create / rename / delete."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.exceptions import BadRequestError, ValidationError
from pointlessql.services.notebook import _workspace as notebook_workspace_service
from pointlessql.services.notebook import outputs as notebook_outputs_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.post("/api/notebooks/create", status_code=201)
async def api_create_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Create an empty ``.py`` notebook under the workspace root.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        body: JSON body with key ``path`` (required, relative path
            ending in ``.py``).

    Returns:
        JSON ``{"path": "<relative>"}`` on success; 422 with the
        :class:`ValidationError` envelope on bad input.

    Raises:
        ValidationError: When ``body.path`` is missing / non-string,
            escapes the workspace root, has the wrong suffix, or
            already exists on disk.
    """
    require_user(request)
    raw_path = body.get("path") if isinstance(body, dict) else None
    if not isinstance(raw_path, str):
        raise ValidationError("body.path must be a string")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    resolved = notebook_workspace_service.create_empty_notebook(notebooks_dir, raw_path)
    relative = str(resolved.relative_to(notebooks_dir))
    logger.info(
        "created notebook %s (%s)",
        relative,
        request.state.user.get("email") if hasattr(request.state, "user") else "?",
    )
    return JSONResponse({"path": relative}, status_code=201)


@router.post("/api/notebooks/rename")
async def api_rename_notebook(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Move a notebook to a new path under the workspace root.

    Re-keys persisted ``notebook_outputs`` rows so the editor at the
    new path replays the prior session's outputs verbatim.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        body: JSON body with keys ``from_path`` and ``to_path``.

    Returns:
        JSON ``{"from_path": ..., "to_path": ...}`` on success.

    Raises:
        ValidationError: On any of the shared resolver guards
            (traversal, suffix, missing source, existing target).
    """
    require_user(request)
    from_path = body.get("from_path") if isinstance(body, dict) else None
    to_path = body.get("to_path") if isinstance(body, dict) else None
    if not isinstance(from_path, str) or not isinstance(to_path, str):
        raise ValidationError("body.from_path and body.to_path must be strings")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    notebook_workspace_service.rename_notebook(notebooks_dir, from_path, to_path)
    notebook_outputs_service.rename_path(
        request.app.state.session_factory,
        from_path,
        to_path,
    )
    logger.info("renamed notebook %s -> %s", from_path, to_path)
    return JSONResponse({"from_path": from_path, "to_path": to_path})


@router.delete("/api/notebooks/delete")
async def api_delete_notebook(
    request: Request,
    path: str = Query(..., min_length=1),
    confirm: bool = Query(False),
) -> JSONResponse:
    """Delete a notebook + cascade its persisted outputs.

    The confirm-flag keeps a stray ``DELETE /api/notebooks/delete``
    from a misconfigured client from wiping a file silently — the
    browser editor flips it to ``true`` after the user OKs the
    confirm modal.

    Args:
        request: Incoming FastAPI request; any authenticated user.
        path: Relative path of the notebook to delete.
        confirm: Must be ``true`` to actually delete; ``false`` is
            a 400 with a clear envelope.

    Returns:
        JSON ``{"path": ...}`` on success.

    Raises:
        BadRequestError: When ``confirm`` is not ``true`` (rendered
            as a 400) — the browser editor sets it after the
            confirm-modal pick; curl callers must opt in
            explicitly.
    """
    require_user(request)
    if not confirm:
        # bare-http-ok: explicit opt-in flag for a destructive
        # delete route; converting to a domain exception would add
        # no information beyond the literal "confirm=true required"
        # detail string is special-cased by the browser modal.
        raise BadRequestError("confirm=true required")
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    notebook_workspace_service.delete_notebook(notebooks_dir, path)
    notebook_outputs_service.clear_path(request.app.state.session_factory, path)
    logger.info("deleted notebook %s", path)
    return JSONResponse({"path": path})
