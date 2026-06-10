"""Shared post-accept authentication step for WebSocket routes.

Starlette HTTP middleware does not run for WebSocket upgrades, so
every WS route re-resolves the caller via
:func:`pointlessql.api.ws_auth.resolve_websocket_user` and closes
the (already accepted) socket when no identity resolves.  The chat
surfaces and the co-edit hubs each duplicated that resolve-or-close
step; :func:`authenticate_or_close` consolidates it while keeping
each consumer's wire bytes — close code, close reason, and the
optional api-key-principal rejection — exactly as before via
parameters.

Deliberately out of scope:

* ``websocket.accept()`` and any feature gates — the order of
  accept / gate / auth differs per consumer, so those stay in the
  route functions.
* The notebook-kernel WS, which closes *before* accepting (a
  different wire behavior) and therefore keeps calling
  :func:`resolve_websocket_user` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pointlessql.api.ws_auth import resolve_websocket_user

if TYPE_CHECKING:
    from fastapi import WebSocket

    from pointlessql.types import UserInfo


async def authenticate_or_close(
    websocket: WebSocket,
    *,
    close_reason: str | None = "not_authenticated",
    reject_api_key_principals: bool = False,
    api_key_close_code: int = 4403,
    api_key_close_reason: str | None = None,
) -> UserInfo | None:
    """Resolve the caller's identity or close the socket with 4401.

    Must be called after ``websocket.accept()`` — closing an
    accepted socket is what lets the browser observe the close code
    and reason instead of a generic handshake failure.

    Args:
        websocket: The already-accepted WebSocket connection.
        close_reason: Reason string for the 4401 close frame when no
            identity resolves; ``None`` sends an empty reason (the
            co-edit hubs' historical bytes).
        reject_api_key_principals: When ``True``, synthetic api-key
            principals (``id == 0``) are also rejected — browser-only
            surfaces such as the co-edit hubs lock out Bearer-key
            callers.
        api_key_close_code: Close code for the api-key rejection.
        api_key_close_reason: Reason string for the api-key
            rejection; ``None`` sends an empty reason.

    Returns:
        The resolved :class:`UserInfo`, or ``None`` when the socket
        was closed (the route should simply ``return``).
    """
    user = resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401, reason=close_reason)
        return None
    if reject_api_key_principals and int(user.get("id") or 0) == 0:
        await websocket.close(code=api_key_close_code, reason=api_key_close_reason)
        return None
    return user
