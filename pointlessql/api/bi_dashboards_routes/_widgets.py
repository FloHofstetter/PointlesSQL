"""Widget CRUD + gridstack layout bulk-save endpoints."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.bi_dashboards_routes._shared import (
    ensure_can_edit,
    ensure_dashboard,
    serialize_widget,
)
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.services import bi_dashboards as bi_service

router = APIRouter()

_WIDGET_FIELDS = ("title", "sql_text", "saved_query_id", "markdown", "chart_spec", "position")


@router.post("/api/bi/dashboards/{slug}/widgets")
async def api_add_widget(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add a widget to a dashboard (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        body: ``{"kind", "title"?, "sql_text"?, "saved_query_id"?,
            "markdown"?, "chart_spec"?, "position"?}``.

    Returns:
        The serialized widget row.

    Raises:
        ValidationError: On an unknown kind or inconsistent source.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    factory = request.app.state.session_factory
    try:
        row = bi_service.add_widget(
            factory,
            dashboard_id=dashboard.id,
            kind=str(body.get("kind", "")),
            title=body.get("title"),
            sql_text=body.get("sql_text"),
            saved_query_id=body.get("saved_query_id"),
            markdown=body.get("markdown"),
            chart_spec=body.get("chart_spec"),
            position=body.get("position"),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "bi_widget.created",
        f"bi_dashboard:{dashboard.slug}",
        {"widget_id": row.id, "kind": row.kind},
    )
    return serialize_widget(row)


@router.patch("/api/bi/dashboards/{slug}/widgets/{widget_id}")
async def api_update_widget(
    request: Request,
    slug: str,
    widget_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch a widget's fields (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        widget_id: Widget primary key.
        body: Any subset of the widget fields.

    Returns:
        The serialized refreshed widget.

    Raises:
        ResourceNotFoundError: When the widget is not on this
            dashboard.
        ValidationError: When the patch leaves the widget without a
            consistent data source.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    factory = request.app.state.session_factory
    existing = bi_service.get_widget(factory, dashboard_id=dashboard.id, widget_id=widget_id)
    if existing is None:
        raise ResourceNotFoundError(f"Widget {widget_id} not found on '{slug}'.")
    kwargs = {field: body[field] for field in _WIDGET_FIELDS if field in body}
    try:
        row = bi_service.update_widget(factory, widget_id=widget_id, **kwargs)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    assert row is not None  # existence ensured above  # noqa: S101
    await audit(
        request,
        "bi_widget.updated",
        f"bi_dashboard:{dashboard.slug}",
        {"widget_id": widget_id, "fields": sorted(kwargs)},
    )
    return serialize_widget(row)


@router.delete("/api/bi/dashboards/{slug}/widgets/{widget_id}")
async def api_delete_widget(request: Request, slug: str, widget_id: int) -> dict[str, Any]:
    """Remove a widget (owner or admin)."""
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    factory = request.app.state.session_factory
    existing = bi_service.get_widget(factory, dashboard_id=dashboard.id, widget_id=widget_id)
    deleted = (
        bi_service.delete_widget(factory, widget_id=widget_id) if existing is not None else False
    )
    if deleted:
        await audit(
            request,
            "bi_widget.deleted",
            f"bi_dashboard:{dashboard.slug}",
            {"widget_id": widget_id},
        )
    return {"deleted": deleted}


@router.put("/api/bi/dashboards/{slug}/layout")
async def api_save_layout(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Bulk-save widget rectangles after a gridstack drag (owner/admin).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        body: ``{"positions": {"<widget_id>": {"x","y","w","h"}}}``.

    Returns:
        ``{"updated": int}``.

    Raises:
        ValidationError: When ``positions`` is not an object.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    factory = request.app.state.session_factory
    positions_raw = body.get("positions")
    if not isinstance(positions_raw, dict):
        raise ValidationError("positions must be an object of widget_id → rect")
    try:
        positions: dict[int, dict[str, Any]] = {
            int(key): dict(cast("dict[str, Any]", rect))
            for key, rect in cast("dict[str, Any]", positions_raw).items()
        }
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"malformed positions payload: {exc}") from exc
    updated = bi_service.update_layout(factory, dashboard_id=dashboard.id, positions=positions)
    await audit(
        request,
        "bi_dashboard.layout",
        f"bi_dashboard:{dashboard.slug}",
        {"updated": updated},
    )
    return {"updated": updated}
