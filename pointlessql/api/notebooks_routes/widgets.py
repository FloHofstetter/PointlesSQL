"""Notebook widget CRUD routes."""

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
from pointlessql.services.notebook import widgets as notebook_widgets_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    """Resolve a ``?path=`` query into the stable notebook UUID."""
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.get("/api/notebooks/widgets")
async def api_list_widgets(request: Request, path: str = Query(..., min_length=1)) -> JSONResponse:
    """List every widget on a notebook in display order.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path.

    Returns:
        JSON ``{path, notebook_id, widgets: [...]}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        widgets = notebook_widgets_service.list_widgets(session, notebook_id=notebook_id)
    return JSONResponse({"path": path, "notebook_id": notebook_id, "widgets": widgets})


@router.put("/api/notebooks/widgets")
async def api_upsert_widget(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Insert or replace one widget definition.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{path, name, widget_kind, label, config,
            default_value?, position?}``.

    Returns:
        JSON of the persisted widget row.

    Raises:
        ValidationError: On bad input shape.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    name = body.get("name")
    widget_kind = body.get("widget_kind")
    label = body.get("label")
    config = body.get("config")
    if not isinstance(path, str) or not isinstance(name, str):
        raise ValidationError("body.path and body.name must be strings")
    if not isinstance(widget_kind, str):
        raise ValidationError("body.widget_kind must be a string")
    if not isinstance(label, str):
        raise ValidationError("body.label must be a string")
    if not isinstance(config, dict):
        raise ValidationError("body.config must be a JSON object")
    default_value = body.get("default_value")
    position_raw = body.get("position", 0)
    position = int(position_raw) if isinstance(position_raw, (int, float)) else 0

    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_widgets_service.upsert_widget(
            session,
            notebook_id=notebook_id,
            name=name,
            widget_kind=widget_kind,
            label=label,
            config=config,
            default_value=default_value,
            position=position,
        )
        envelope = notebook_widgets_service.widget_to_envelope(row)
        session.commit()
    return JSONResponse(envelope)


@router.delete("/api/notebooks/widgets")
async def api_delete_widget(
    request: Request,
    path: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
) -> JSONResponse:
    """Delete one widget; idempotent.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path.
        name: Widget identifier.

    Returns:
        JSON ``{removed: bool}``.
    """
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        removed = notebook_widgets_service.delete_widget(
            session, notebook_id=notebook_id, name=name
        )
        session.commit()
    return JSONResponse({"removed": removed})


@router.post("/api/notebooks/widgets/resolve")
async def api_resolve_widget_values(
    request: Request, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    """Return the ``name → value`` map the kernel will see.

    Args:
        request: Incoming request; any authenticated user.
        body: JSON ``{path, overrides?: {name: value, …}}``.

    Returns:
        JSON ``{values: {name: value, …}}``.

    Raises:
        ValidationError: When ``body`` is not a JSON object or
            ``path`` is missing.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    overrides_raw = body.get("overrides")
    if not isinstance(path, str):
        raise ValidationError("body.path must be a string")
    overrides = overrides_raw if isinstance(overrides_raw, dict) else None
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        values = notebook_widgets_service.resolve_widget_values(
            session, notebook_id=notebook_id, overrides=overrides
        )
    return JSONResponse({"values": values})
