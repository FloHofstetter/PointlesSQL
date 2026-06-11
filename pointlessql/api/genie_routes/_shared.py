"""Serializers + guards shared across the Genie route family."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import PermissionDeniedError, ResourceNotFoundError
from pointlessql.models.genie import GenieMessage, GenieSpace, GenieTrustedAsset
from pointlessql.services import genie as genie_service
from pointlessql.types import UserInfo


def serialize_space(row: GenieSpace, *, asset_count: int | None = None) -> dict[str, Any]:
    """Project a space row to a JSON-safe dict (JSON columns parsed)."""
    body: dict[str, Any] = {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "instructions": row.instructions,
        "tables": genie_service.space_tables(row),
        "metric_views": genie_service.space_metric_views(row),
        "owner_id": row.owner_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if asset_count is not None:
        body["asset_count"] = asset_count
    return body


def serialize_asset(row: GenieTrustedAsset) -> dict[str, Any]:
    """Project a trusted-asset row to a JSON-safe dict."""
    return {
        "id": row.id,
        "question": row.question,
        "sql_text": row.sql_text,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_message(row: GenieMessage) -> dict[str, Any]:
    """Project a transcript row to a JSON-safe dict."""
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "sql_text": row.sql_text,
        "status": row.status,
        "error": row.error,
        "feedback": row.feedback,
        "user_id": row.user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def ensure_space(request: Request, slug: str) -> GenieSpace:
    """Return the active workspace's space or raise a 404.

    Args:
        request: Incoming FastAPI request.
        slug: Space slug from the URL.

    Returns:
        The detached space row.

    Raises:
        ResourceNotFoundError: When no space with *slug* exists in
            the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = genie_service.get_space(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"Genie space '{slug}' not found.")
    return row


def ensure_can_edit(request: Request, space: GenieSpace) -> UserInfo:
    """Gate curation mutations to the owner + admins.

    Args:
        request: Incoming FastAPI request.
        space: The space being mutated.

    Returns:
        The acting user's :class:`UserInfo`.

    Raises:
        PermissionDeniedError: When the caller is neither the owner
            nor an admin.
    """
    user = get_user(request)
    if not user["is_admin"] and int(user["id"]) != space.owner_id:
        raise PermissionDeniedError("only the space owner or an admin can modify it")
    return user
