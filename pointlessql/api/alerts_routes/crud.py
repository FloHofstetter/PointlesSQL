"""``/api/alerts`` CRUD — list / create / get / patch / delete.

Visibility model: non-admin sees only their own alerts; missing vs.
forbidden collapses to 404 so private slugs are not discoverable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


@router.get("/api/alerts")
async def api_list_alerts(request: Request) -> list[dict[str, Any]]:
    """List alerts visible to the caller.

    Non-admin callers only see their own alerts; admin sees every row.

    Args:
        request: Incoming request (for the current user).

    Returns:
        Serialised alerts with embedded destinations.
    """
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = get_user(request)
    return await asyncio.to_thread(
        alerts_service.list_visible,
        factory,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )


@router.post("/api/alerts")
async def api_create_alert(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new alert owned by the caller.

    Args:
        request: Incoming request.
        body: JSON body with ``title``, ``saved_query_id``,
            ``cron_expr``, ``condition_op``, ``threshold`` keys;
            optional ``is_active`` (defaults ``True``).

    Returns:
        The serialised alert dict.

    Raises:
        ValidationError: If any required field fails validation.
    """  # noqa: DOC502 — ValidationError raised by service layer
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ValidationError("Alerts are not available in this deployment.")
    user = get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        alerts_service.create_alert,
        factory,
        owner_id=user["id"],
        title=str(payload.get("title", "")),
        saved_query_id=int(payload.get("saved_query_id") or 0),
        cron_expr=str(payload.get("cron_expr", "")),
        condition_op=str(payload.get("condition_op", "gt")),
        threshold=int(payload.get("threshold", 0)),
        is_active=bool(payload.get("is_active", True)),
    )
    await audit(
        request,
        "alert.created",
        f"alert:{row['slug']}",
        {"title": row["title"], "cron_expr": row["cron_expr"]},
    )
    return row


@router.get("/api/alerts/{slug}")
async def api_get_alert(request: Request, slug: str) -> dict[str, Any]:
    """Return a single alert by slug.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        Serialised alert with destinations.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    row = await asyncio.to_thread(
        alerts_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    return row


@router.patch("/api/alerts/{slug}")
async def api_update_alert(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch an alert in place.  Only owner + admin may mutate.

    Args:
        request: Incoming request.
        slug: Alert slug.
        body: Partial update payload.

    Returns:
        Updated alert dict.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below; ValidationError bubbles from service
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        alerts_service.update_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        cron_expr=payload.get("cron_expr") if isinstance(payload.get("cron_expr"), str) else None,
        condition_op=payload.get("condition_op")
        if isinstance(payload.get("condition_op"), str)
        else None,
        threshold=int(payload["threshold"]) if isinstance(payload.get("threshold"), int) else None,
        is_active=bool(payload["is_active"]) if "is_active" in payload else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request,
        "alert.updated",
        f"alert:{slug}",
        {"is_active": row["is_active"]},
    )
    return row


@router.delete("/api/alerts/{slug}", status_code=204)
async def api_delete_alert(request: Request, slug: str) -> Response:
    """Delete an alert, its destinations, events, and backing Job.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    ok = await asyncio.to_thread(
        alerts_service.delete_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(request, "alert.deleted", f"alert:{slug}", None)
    return Response(status_code=204)
