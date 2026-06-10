"""Per-user feed-token endpoints: ``GET/POST /api/me/feed-token``.

Cookie-authenticated only.  ``GET`` materialises the token on first
access; ``POST .../rotate`` mints a fresh one and audits the rotation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.alerts_routes._helpers import rotate_or_fetch_feed_token
from pointlessql.api.dependencies import get_user
from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


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
    token = await run_sync(
        rotate_or_fetch_feed_token,
        factory,
        user["id"],
        False,
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
    token = await run_sync(
        rotate_or_fetch_feed_token,
        factory,
        user["id"],
        True,
    )
    await audit(request, "alert.feed_token_rotated", f"user:{user['id']}", None)
    return {"token": token}
