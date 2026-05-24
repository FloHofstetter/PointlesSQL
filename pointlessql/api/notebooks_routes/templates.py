"""Notebook template-gallery routes.

The gallery lists the starter templates shipped under
``pointlessql/data/notebook_templates/``; the create route copies
one of them into the workspace at a caller-supplied path.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import templates as notebook_templates_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/templates")
async def api_list_notebook_templates(request: Request) -> JSONResponse:
    """Return the starter-template gallery cards.

    Args:
        request: Incoming request; any authenticated user.

    Returns:
        JSON ``{"templates": [...]}`` — each entry has ``id`` /
        ``title`` / ``description`` / ``category`` / ``filename``.
    """
    require_user(request)
    return JSONResponse(
        {"templates": notebook_templates_service.list_templates()}
    )


@router.post("/api/notebooks/from-template", status_code=201)
async def api_create_from_template(
    request: Request, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    """Create a new notebook by copying a starter template.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON with keys ``template_id`` (gallery ``id``) and
            ``path`` (target relative path under ``notebooks_dir``).

    Returns:
        JSON ``{"path": <relative>}`` on success.

    Raises:
        ValidationError: On bad input or unknown template.
    """
    require_user(request)
    template_id = body.get("template_id") if isinstance(body, dict) else None
    dest_path = body.get("path") if isinstance(body, dict) else None
    if not isinstance(template_id, str) or not isinstance(dest_path, str):
        raise ValidationError(
            "body.template_id and body.path must be strings"
        )
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    resolved = notebook_templates_service.create_from_template(
        notebooks_dir=notebooks_dir,
        template_id=template_id,
        dest_path=dest_path,
    )
    relative = str(resolved.relative_to(notebooks_dir))
    logger.info(
        "created notebook %s from template %s", relative, template_id
    )
    return JSONResponse({"path": relative}, status_code=201)
