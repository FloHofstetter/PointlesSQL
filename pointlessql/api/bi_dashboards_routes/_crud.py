"""Dashboard CRUD + publish/unpublish endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.bi_dashboards_routes._shared import (
    ensure_can_edit,
    ensure_dashboard,
    serialize_dashboard,
    serialize_widget,
)
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import PermissionDeniedError, ValidationError
from pointlessql.services import bi_dashboards as bi_service

router = APIRouter()


@router.get("/api/bi/dashboards")
async def api_list_dashboards(request: Request) -> dict[str, Any]:
    """List the active workspace's dashboards with widget counts."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    pairs = bi_service.list_dashboards(factory, workspace_id=workspace_id)
    return {"dashboards": [serialize_dashboard(row, widget_count=count) for row, count in pairs]}


@router.post("/api/bi/dashboards")
async def api_create_dashboard(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create an empty dashboard.

    Args:
        request: Incoming FastAPI request.
        body: ``{"title": str, "description"?: str}``.

    Returns:
        The serialized dashboard row.

    Raises:
        ValidationError: On a missing/empty title.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to create dashboards")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("title must be a non-empty string")
    description = body.get("description")
    try:
        row = bi_service.create_dashboard(
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
        "bi_dashboard.created",
        f"bi_dashboard:{row.slug}",
        {"id": row.id, "title": row.title},
    )
    return serialize_dashboard(row, widget_count=0)


@router.get("/api/bi/dashboards/{slug}")
async def api_get_dashboard(request: Request, slug: str) -> dict[str, Any]:
    """Return one dashboard with its widgets."""
    row = ensure_dashboard(request, slug)
    factory = request.app.state.session_factory
    widgets = bi_service.list_widgets(factory, dashboard_id=row.id)
    body = serialize_dashboard(row, widget_count=len(widgets))
    body["widgets"] = [serialize_widget(w) for w in widgets]
    return body


@router.patch("/api/bi/dashboards/{slug}")
async def api_update_dashboard(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch title / description / params (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        body: Any of ``{"title", "description", "params"}``.

    Returns:
        The serialized refreshed dashboard.

    Raises:
        ValidationError: On an empty title or malformed params.
    """
    row = ensure_dashboard(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    kwargs: dict[str, Any] = {}
    if "title" in body:
        kwargs["title"] = body["title"]
    if "description" in body:
        kwargs["description"] = body["description"]
    if "params" in body:
        kwargs["params"] = body["params"]
    try:
        updated = bi_service.update_dashboard(factory, dashboard_id=row.id, **kwargs)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    assert updated is not None  # ensured above  # noqa: S101
    await audit(
        request,
        "bi_dashboard.updated",
        f"bi_dashboard:{row.slug}",
        {"fields": sorted(kwargs)},
    )
    return serialize_dashboard(updated)


@router.delete("/api/bi/dashboards/{slug}")
async def api_delete_dashboard(request: Request, slug: str) -> dict[str, Any]:
    """Delete a dashboard and its widgets (owner or admin)."""
    row = ensure_dashboard(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    deleted = bi_service.delete_dashboard(factory, dashboard_id=row.id)
    if deleted:
        await audit(
            request,
            "bi_dashboard.deleted",
            f"bi_dashboard:{row.slug}",
            {"id": row.id},
        )
    return {"deleted": deleted}


@router.post("/api/bi/dashboards/{slug}/publish")
async def api_publish_dashboard(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Publish or unpublish a dashboard (owner or admin).

    Publishing mints a public token; the dashboard then renders
    unauthenticated under ``/bi/public/{token}`` with widget queries
    running as the owner (embedded-credentials model).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        body: ``{"publish": bool}``.

    Returns:
        ``{"is_published": bool, "public_token": str | None}``.
    """
    row = ensure_dashboard(request, slug)
    ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    publish = bool(body.get("publish"))
    token = bi_service.set_publish(factory, dashboard_id=row.id, publish=publish)
    await audit(
        request,
        "bi_dashboard.published" if publish else "bi_dashboard.unpublished",
        f"bi_dashboard:{row.slug}",
        {"id": row.id},
    )
    return {"is_published": token is not None, "public_token": token}
