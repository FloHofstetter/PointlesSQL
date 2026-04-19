"""Alerts API + feed routes (Phase 12.5 / Sprint 55).

Sprint 87 split out of ``api/main.py``.  Owns:

* The ``/api/alerts`` CRUD (list / create / get / patch / delete).
* The destinations sub-resource (``POST/DELETE /api/alerts/{slug}/
  destinations``).
* The per-user feed-token endpoints (``GET /api/me/feed-token`` +
  ``POST /api/me/feed-token/rotate``).
* The two unauthenticated pull-feed endpoints
  (``/alerts/feed.atom`` + ``/alerts/feed.json``) — these
  authenticate via the opaque ``?token=…`` query string, not the
  session cookie, so the auth middleware's ``PUBLIC_PREFIXES``
  exempts them and the route handlers themselves reject unknown
  tokens with 401.
* The two HTML pages (``/alerts`` list + ``/alerts/{slug}`` detail).

Visibility model is unchanged from the pre-split shape: non-admin
sees only their own alerts; missing-vs-forbidden collapses to 404
so private slugs are not discoverable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import ValidationError
from pointlessql.services import saved_queries as saved_queries_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def base_url(request: Request) -> str:
    """Return the absolute base URL for the running deployment.

    Args:
        request: Incoming request used to build the URL.

    Returns:
        ``<scheme>://<host>`` without trailing slash.
    """
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def rotate_or_fetch_feed_token(
    factory: Any, user_id: int, rotate: bool = False,
) -> str:
    """Return the caller's feed token, materialising one on first access.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Authenticated user id.
        rotate: When ``True`` force a fresh token even if one exists.

    Returns:
        URL-safe opaque token.

    Raises:
        RuntimeError: When the authenticated user id no longer
            resolves to a row (shouldn't happen since the request
            already authenticated, but kept explicit).
    """
    import secrets as _secrets

    from pointlessql.models import User

    with factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        if not user.feed_token or rotate:
            user.feed_token = _secrets.token_urlsafe(32)
            session.commit()
            session.refresh(user)
        return user.feed_token or ""


def user_for_feed_token(factory: Any, token: str) -> Any:
    """Return the :class:`User` matching *token*, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        token: Opaque token from the query string.

    Returns:
        The user row or ``None`` when the token does not resolve.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import User

    if not token:
        return None
    with factory() as session:
        return session.scalar(
            _select(User).where(User.feed_token == token),
        )


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
    request: Request, body: dict[str, Any] = Body(...),
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
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    return row


@router.patch("/api/alerts/{slug}")
async def api_update_alert(
    request: Request, slug: str, body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Partially update an alert.  Only owner + admin may mutate.

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
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        cron_expr=payload.get("cron_expr")
        if isinstance(payload.get("cron_expr"), str) else None,
        condition_op=payload.get("condition_op")
        if isinstance(payload.get("condition_op"), str) else None,
        threshold=int(payload["threshold"])
        if isinstance(payload.get("threshold"), int) else None,
        is_active=bool(payload["is_active"])
        if "is_active" in payload else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request, "alert.updated", f"alert:{slug}",
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
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(request, "alert.deleted", f"alert:{slug}", None)
    return Response(status_code=204)


@router.post("/api/alerts/{slug}/destinations")
async def api_add_alert_destination(
    request: Request, slug: str, body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add a webhook or feed destination to an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        body: Body with ``kind`` (``webhook`` / ``feed``), plus
            ``webhook_url`` / ``hmac_secret`` when relevant.

    Returns:
        The new destination dict.

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
    dest = await asyncio.to_thread(
        alerts_service.add_destination,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        kind=str(payload.get("kind", "webhook")),
        webhook_url=payload.get("webhook_url")
        if isinstance(payload.get("webhook_url"), str) else None,
        hmac_secret=payload.get("hmac_secret")
        if isinstance(payload.get("hmac_secret"), str) else None,
    )
    if dest is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request, "alert.destination_added", f"alert:{slug}",
        {"kind": dest["kind"], "has_hmac": dest["has_hmac"]},
    )
    return dest


@router.delete(
    "/api/alerts/{slug}/destinations/{destination_id}", status_code=204,
)
async def api_delete_alert_destination(
    request: Request, slug: str, destination_id: int,
) -> Response:
    """Remove a destination from an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        destination_id: Row id of the destination.

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
        alerts_service.delete_destination,
        factory, slug, destination_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request, "alert.destination_removed",
        f"alert:{slug}/destination:{destination_id}", None,
    )
    return Response(status_code=204)


@router.get("/api/me/feed-token")
async def api_get_feed_token(request: Request) -> dict[str, str]:
    """Return the caller's pull-feed token, creating one on first call.

    Args:
        request: Incoming request.

    Returns:
        Dict with ``token`` key.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"token": ""}
    user = get_user(request)
    token = await asyncio.to_thread(
        rotate_or_fetch_feed_token, factory, user["id"], False,
    )
    return {"token": token}


@router.post("/api/me/feed-token/rotate")
async def api_rotate_feed_token(request: Request) -> dict[str, str]:
    """Rotate the caller's feed token, invalidating existing subscribers.

    Args:
        request: Incoming request.

    Returns:
        Dict with the new ``token``.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"token": ""}
    user = get_user(request)
    token = await asyncio.to_thread(
        rotate_or_fetch_feed_token, factory, user["id"], True,
    )
    await audit(request, "alert.feed_token_rotated", f"user:{user['id']}", None)
    return {"token": token}


@router.get("/alerts/feed.atom")
async def feed_atom(request: Request, token: str = "") -> Response:
    """Serve a per-owner Atom 1.0 feed of fired alerts.

    Args:
        request: Incoming request (used for base-URL building).
        token: Opaque per-user token from the query string.

    Returns:
        200 with Atom XML body on success, 401 on token mismatch.
    """
    from pointlessql.services import alert_feeds
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=401)
    user = await asyncio.to_thread(user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await asyncio.to_thread(
        alerts_service.list_events_for_owner,
        factory, user.id, since=cutoff, limit=200,
    )
    body = alert_feeds.render_atom(
        events, user_email=user.email, base_url=base_url(request),
    )
    return Response(
        content=body,
        media_type="application/atom+xml; charset=utf-8",
    )


@router.get("/alerts/feed.json")
async def feed_json(request: Request, token: str = "") -> Response:
    """Serve a per-owner JSON Feed 1.1 document of fired alerts.

    Args:
        request: Incoming request.
        token: Opaque per-user token.

    Returns:
        200 with JSON Feed body on success, 401 on token mismatch.
    """
    from pointlessql.services import alert_feeds
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=401)
    user = await asyncio.to_thread(user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await asyncio.to_thread(
        alerts_service.list_events_for_owner,
        factory, user.id, since=cutoff, limit=200,
    )
    body = alert_feeds.render_json_feed(
        events, user_email=user.email, base_url=base_url(request),
    )
    return JSONResponse(content=body, media_type="application/feed+json")


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
    return _templates(request).TemplateResponse(
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
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if alert_row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    events = await asyncio.to_thread(
        alerts_service.list_events_for_alert,
        factory, alert_row["id"], limit=50,
    )
    return _templates(request).TemplateResponse(
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
