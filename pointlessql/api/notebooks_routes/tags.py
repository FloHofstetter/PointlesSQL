"""Notebook tag CRUD routes (Phase 98.B).

Tags categorise a whole notebook (``etl`` / ``draft`` / ``prod`` /
etc.).  All routes are workspace-scoped via the standard cookie-user
gate; the service layer (:mod:`pointlessql.services.notebook.tags`)
normalises tag text before persistence.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import tags as notebook_tags_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    """Resolve a ``?path=`` query into the stable notebook UUID.

    Args:
        request: Incoming request.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        The notebook UUID — minted on demand if this is the first
        time the path is seen.
    """
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/tags")
async def api_list_notebook_tags(
    request: Request, path: str
) -> JSONResponse:
    """List every tag attached to a notebook.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path.

    Returns:
        JSON ``{"path": ..., "notebook_id": ..., "tags": [...]}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_tags_service.list_tags(session, notebook_id)
    return JSONResponse(
        {
            "path": path,
            "notebook_id": notebook_id,
            "tags": rows,
            "curated": list(notebook_tags_service.CURATED_NOTEBOOK_TAGS),
        }
    )


@router.post("/api/notebooks/tags")
async def api_add_notebook_tag(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Attach a tag to a notebook; idempotent.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{"path": <relative>, "tag": <text>}``.

    Returns:
        JSON ``{"tag": <normalised>}``.

    Raises:
        ValidationError: On bad input or tag-cap reached.
    """
    require_user(request)
    path = body.get("path") if isinstance(body, dict) else None
    raw_tag = body.get("tag")
    if not isinstance(path, str) or not isinstance(raw_tag, str):
        raise ValidationError("body.path and body.tag must be strings")
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        tag = notebook_tags_service.add_tag(
            session,
            notebook_id=notebook_id,
            raw_tag=raw_tag,
        )
        session.commit()
    logger.info("notebook %s tagged %r", notebook_id, tag)
    return JSONResponse({"tag": tag, "notebook_id": notebook_id})


@router.delete("/api/notebooks/tags")
async def api_remove_notebook_tag(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Detach a tag from a notebook.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{"path": <relative>, "tag": <text>}``.

    Returns:
        JSON ``{"removed": bool}``.

    Raises:
        ValidationError: On bad input shape.
    """
    require_user(request)
    path = body.get("path") if isinstance(body, dict) else None
    raw_tag = body.get("tag")
    if not isinstance(path, str) or not isinstance(raw_tag, str):
        raise ValidationError("body.path and body.tag must be strings")
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        removed = notebook_tags_service.remove_tag(
            session,
            notebook_id=notebook_id,
            raw_tag=raw_tag,
        )
        session.commit()
    return JSONResponse({"removed": removed, "notebook_id": notebook_id})
