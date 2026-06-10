"""Unauthenticated pull-feed endpoints (Atom + JSON Feed).

These two routes authenticate via the opaque ``?token=...`` query
string rather than the session cookie.  The auth middleware exempts
them via ``PUBLIC_PREFIXES`` and the handlers themselves reject
unknown tokens with 401 so private alert histories are never exposed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from pointlessql.api.alerts_routes._helpers import base_url, user_for_feed_token
from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


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
    user = await run_sync(user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await run_sync(
        alerts_service.list_events_for_owner,
        factory,
        user.id,
        since=cutoff,
        limit=200,
    )
    body = alert_feeds.render_atom(
        events,
        user_email=user.email,
        base_url=base_url(request),
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
    user = await run_sync(user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await run_sync(
        alerts_service.list_events_for_owner,
        factory,
        user.id,
        since=cutoff,
        limit=200,
    )
    body = alert_feeds.render_json_feed(
        events,
        user_email=user.email,
        base_url=base_url(request),
    )
    return JSONResponse(content=body, media_type="application/feed+json")
