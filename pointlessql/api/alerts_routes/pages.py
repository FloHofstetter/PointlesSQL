"""HTML pages for the alerts surface: list + detail.

Both pages share the visibility model with the JSON CRUD: non-admin
sees their own alerts, missing-vs-forbidden collapses to 404.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, get_user
from pointlessql.services import saved_queries as saved_queries_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request) -> HTMLResponse:
    """Render the alerts list page.

    Args:
        request: Incoming request.

    Returns:
        HTML page with the list of visible alerts.
    """
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    user = get_user(request)
    alerts: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []
    if factory is not None:
        alerts = await asyncio.to_thread(
            alerts_service.list_visible,
            factory,
            user_id=user["id"],
            is_admin=bool(user.get("is_admin", False)),
        )
        saved = await asyncio.to_thread(
            saved_queries_service.list_visible,
            factory,
            user_id=user["id"],
            is_admin=bool(user.get("is_admin", False)),
            limit=200,
        )
    return get_templates(request).TemplateResponse(
        request,
        "pages/alerts.html",
        {
            "alerts": alerts,
            "saved_queries": saved,
            "active_page": "alerts",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@router.get("/alerts/{slug}", response_class=HTMLResponse)
async def alert_detail_page(request: Request, slug: str) -> HTMLResponse:
    """Render the alert detail page with recent events.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        HTML page with the alert's destinations + last 50 events.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    alert_row = await asyncio.to_thread(
        alerts_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if alert_row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    events = await asyncio.to_thread(
        alerts_service.list_events_for_alert,
        factory,
        alert_row["id"],
        limit=50,
    )
    return get_templates(request).TemplateResponse(
        request,
        "pages/alert_detail.html",
        {
            "alert": alert_row,
            "events": events,
            "active_page": "alerts",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
