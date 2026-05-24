"""Shared WebSocket authentication helper.

Starlette's HTTP ``BaseHTTPMiddleware`` does not run for WebSocket
upgrades, so every WebSocket route has to re-run the
cookie + Bearer-key resolution path that the regular HTTP
``auth_middleware`` would have handled. This introduces a
second WebSocket surface (the SQL-chat panel) alongside the
notebook-kernel WS — both call :func:`resolve_websocket_user`
rather than copy-pasting the same 25 lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import auth as auth_service
from pointlessql.types import UserInfo

if TYPE_CHECKING:
    from fastapi import WebSocket


def resolve_websocket_user(websocket: WebSocket) -> UserInfo | None:
    """Resolve the caller's identity on a WebSocket upgrade.

    Order:

    1. ``pql_session`` cookie → JWT verification → :class:`UserInfo`.
    2. ``Authorization: Bearer ...`` header → DB-backed api_keys
       verification → synthetic :class:`UserInfo` carrying the
       key name and scope flags.

    Args:
        websocket: The incoming WebSocket connection.

    Returns:
        The resolved :class:`UserInfo`, or ``None`` if neither
        identification path produced an identity (route closes
        4401).
    """
    factory = getattr(websocket.app.state, "session_factory", None)
    settings = getattr(websocket.app.state, "settings", None)
    if factory is None or settings is None:
        return None
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if token is not None:
        user = auth_service.get_current_user(
            factory,
            token,
            settings.auth.secret_key,
            previous_key=settings.auth.secret_key_previous,
        )
        if user is not None:
            return user
    entry = api_keys_service.verify_bearer(
        websocket.headers.get("authorization"),
        factory,
    )
    if entry is None:
        return None
    return UserInfo(
        id=0,
        email=f"api_key:{entry.name}",
        display_name=entry.name,
        is_admin=False,
        is_supervisor=entry.supervisor,
        is_auditor=entry.auditor,
    )
