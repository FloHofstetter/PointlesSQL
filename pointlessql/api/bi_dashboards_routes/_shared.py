"""Serializers + guards shared across the BI-dashboard route family."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import PermissionDeniedError, ResourceNotFoundError
from pointlessql.models.bi_dashboards import BiDashboard, BiDashboardWidget
from pointlessql.services import bi_dashboards as bi_service
from pointlessql.types import UserInfo


def serialize_dashboard(row: BiDashboard, *, widget_count: int | None = None) -> dict[str, Any]:
    """Project a dashboard row to a JSON-safe dict."""
    body: dict[str, Any] = {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "owner_id": row.owner_id,
        "params": json.loads(row.params or "[]"),
        "is_published": row.public_token is not None,
        "public_token": row.public_token,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if widget_count is not None:
        body["widget_count"] = widget_count
    return body


def serialize_widget(row: BiDashboardWidget) -> dict[str, Any]:
    """Project a widget row to a JSON-safe dict (JSON columns parsed)."""
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "sql_text": row.sql_text,
        "saved_query_id": row.saved_query_id,
        "markdown": row.markdown,
        "chart_spec": json.loads(row.chart_spec or "{}"),
        "position": json.loads(row.position or "{}"),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def ensure_dashboard(request: Request, slug: str) -> BiDashboard:
    """Return the active workspace's dashboard or raise a 404.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug from the URL.

    Returns:
        The detached dashboard row.

    Raises:
        ResourceNotFoundError: When no dashboard with *slug* exists
            in the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = bi_service.get_dashboard(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"Dashboard '{slug}' not found.")
    return row


def ensure_can_edit(request: Request, dashboard: BiDashboard) -> UserInfo:
    """Gate mutations to the owner + admins.

    Args:
        request: Incoming FastAPI request.
        dashboard: The dashboard being mutated.

    Returns:
        The acting user's :class:`UserInfo`.

    Raises:
        PermissionDeniedError: When the caller is neither the owner
            nor an admin.
    """
    user = get_user(request)
    if not user["is_admin"] and int(user["id"]) != dashboard.owner_id:
        raise PermissionDeniedError("only the dashboard owner or an admin can modify it")
    return user
