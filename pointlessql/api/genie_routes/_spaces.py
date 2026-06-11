"""Genie-space CRUD + trusted assets + transcript listing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.api.genie_routes._shared import (
    ensure_can_edit,
    ensure_space,
    serialize_asset,
    serialize_message,
    serialize_space,
)
from pointlessql.exceptions import PermissionDeniedError, ValidationError
from pointlessql.services import genie as genie_service

router = APIRouter()


@router.get("/api/genie/spaces")
async def api_list_spaces(request: Request) -> dict[str, Any]:
    """List the active workspace's Genie spaces."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = genie_service.list_spaces(factory, workspace_id=workspace_id)
    return {"spaces": [serialize_space(row) for row in rows]}


@router.post("/api/genie/spaces")
async def api_create_space(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create an empty Genie space.

    Args:
        request: Incoming FastAPI request.
        body: ``{"title": str, "description"?: str}``.

    Returns:
        The serialized space row.

    Raises:
        ValidationError: On a missing/empty title.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to create Genie spaces")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("title must be a non-empty string")
    description = body.get("description")
    try:
        row = genie_service.create_space(
            factory,
            workspace_id=workspace_id,
            title=title,
            description=description if isinstance(description, str) else None,
            owner_id=int(user["id"]),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "genie_space.created",
        f"genie_space:{row.slug}",
        {"id": row.id, "title": row.title},
    )
    return serialize_space(row, asset_count=0)


@router.get("/api/genie/spaces/{slug}")
async def api_get_space(request: Request, slug: str) -> dict[str, Any]:
    """Return one space with its trusted assets."""
    row = ensure_space(request, slug)
    factory = request.app.state.session_factory
    assets = genie_service.list_trusted_assets(factory, space_id=row.id)
    body = serialize_space(row, asset_count=len(assets))
    body["assets"] = [serialize_asset(asset) for asset in assets]
    user = get_user(request)
    body["can_edit"] = bool(user["is_admin"]) or int(user["id"]) == row.owner_id
    return body


@router.patch("/api/genie/spaces/{slug}")
async def api_update_space(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch curation fields (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Space slug.
        body: Any of ``{"title", "description", "instructions",
            "tables", "metric_views"}``.

    Returns:
        The serialized refreshed space.

    Raises:
        ValidationError: On an empty title or a malformed FQN list.
    """
    row = ensure_space(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    kwargs: dict[str, Any] = {}
    for field in ("title", "description", "instructions", "tables", "metric_views"):
        if field in body:
            kwargs[field] = body[field]
    try:
        updated = genie_service.update_space(factory, space_id=row.id, **kwargs)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    assert updated is not None  # ensured above  # noqa: S101
    await audit(
        request,
        "genie_space.updated",
        f"genie_space:{row.slug}",
        {"fields": sorted(kwargs)},
    )
    return serialize_space(updated)


@router.delete("/api/genie/spaces/{slug}")
async def api_delete_space(request: Request, slug: str) -> dict[str, Any]:
    """Delete a space, its assets, and its transcript (owner or admin)."""
    row = ensure_space(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    deleted = genie_service.delete_space(factory, space_id=row.id)
    if deleted:
        await audit(
            request,
            "genie_space.deleted",
            f"genie_space:{row.slug}",
            {"id": row.id},
        )
    return {"deleted": deleted}


@router.post("/api/genie/spaces/{slug}/assets")
async def api_add_trusted_asset(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add a trusted Q→SQL example (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Space slug.
        body: ``{"question": str, "sql_text": str}``.

    Returns:
        The serialized asset row.

    Raises:
        ValidationError: On empty fields or SQL that does not parse
            as a single SELECT.
    """
    row = ensure_space(request, slug)
    user = ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    try:
        asset = genie_service.add_trusted_asset(
            factory,
            space_id=row.id,
            question=str(body.get("question") or ""),
            sql_text=str(body.get("sql_text") or ""),
            created_by=int(user["id"]),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "genie_asset.created",
        f"genie_space:{row.slug}",
        {"asset_id": asset.id, "question": asset.question[:120]},
    )
    return serialize_asset(asset)


@router.delete("/api/genie/spaces/{slug}/assets/{asset_id}")
async def api_delete_trusted_asset(request: Request, slug: str, asset_id: int) -> dict[str, Any]:
    """Remove one trusted asset (owner or admin)."""
    row = ensure_space(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    deleted = genie_service.delete_trusted_asset(factory, space_id=row.id, asset_id=asset_id)
    if deleted:
        await audit(
            request,
            "genie_asset.deleted",
            f"genie_space:{row.slug}",
            {"asset_id": asset_id},
        )
    return {"deleted": deleted}


@router.get("/api/genie/spaces/{slug}/messages")
async def api_list_messages(request: Request, slug: str) -> dict[str, Any]:
    """Return the room's shared transcript (last 50 turns)."""
    row = ensure_space(request, slug)
    factory = request.app.state.session_factory
    messages = genie_service.list_messages(factory, space_id=row.id, limit=50)
    return {"messages": [serialize_message(message) for message in messages]}
