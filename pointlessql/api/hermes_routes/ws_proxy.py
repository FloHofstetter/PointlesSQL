"""WebSocket reverse-proxy for the Hermes chat PTY + gateway streams.

The embedded dashboard's Chat tab drives the real Hermes TUI over a
PTY-WebSocket at ``/api/pty`` (and a gateway event stream at
``/api/ws``).  The HTTP proxy can't carry those — WebSockets need an
explicit bridge — so this module accepts the browser upgrade under
``/hermes/...``, authenticates the PointlesSQL admin, opens an upstream
WebSocket to the resolved Hermes instance, and pumps frames both ways.

Auth flows straight through: the embedded SPA already appends the
right credential to its WebSocket URL (a ``?token=`` in loopback mode,
a single-use ``?ticket=`` in gated mode), so the bridge forwards the
incoming query string verbatim and only fills in the token as a
fallback.  The upstream connection is opened from loopback with no
``X-Forwarded-For`` so Hermes' loopback-only WebSocket gate still
recognises the peer as local.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from pointlessql.api.ws_auth import resolve_websocket_user

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["hermes"])


def _build_upstream_url(
    ws_base_url: str,
    upstream_path: str,
    query: str,
    params: dict[str, str],
    token: str | None,
) -> str:
    """Compose the upstream Hermes WebSocket URL.

    Forwards the browser's query string verbatim (it already carries
    the ``token`` / ``ticket`` the SPA chose) and only appends a
    ``token`` when the client sent neither — so a pre-shared token
    still authenticates even if the SPA bootstrap is absent.

    Args:
        ws_base_url: The instance ws base, e.g. ``ws://127.0.0.1:9119``.
        upstream_path: The Hermes path, ``/api/pty`` or ``/api/ws``.
        query: The raw inbound query string (may be empty).
        params: The parsed inbound query params.
        token: The instance's pre-shared token, or ``None`` (gated).

    Returns:
        str: The fully composed upstream WebSocket URL.
    """
    if token and "token" not in params and "ticket" not in params:
        query = f"{query}&token={token}" if query else f"token={token}"
    url = f"{ws_base_url}{upstream_path}"
    return f"{url}?{query}" if query else url


async def _pump(client: WebSocket, upstream: ClientConnection) -> None:
    """Shuttle frames in both directions until either side closes.

    Args:
        client: The browser-facing PointlesSQL WebSocket (already
            accepted).
        upstream: The connected ``websockets`` client to Hermes.
    """

    async def client_to_upstream() -> None:
        try:
            while True:
                msg = await client.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text")
                if text is not None:
                    await upstream.send(text)
                    continue
                data = msg.get("bytes")
                if data is not None:
                    await upstream.send(data)
        except WebSocketDisconnect, ConnectionClosed, RuntimeError:
            pass

    async def upstream_to_client() -> None:
        try:
            async for frame in upstream:
                if isinstance(frame, str):
                    await client.send_text(frame)
                else:
                    await client.send_bytes(frame)
        except ConnectionClosed, RuntimeError:
            pass

    forward = asyncio.create_task(client_to_upstream())
    backward = asyncio.create_task(upstream_to_client())
    _done, pending = await asyncio.wait({forward, backward}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()


async def _proxy_ws(websocket: WebSocket, upstream_path: str) -> None:
    """Authenticate, resolve the instance, and bridge one WebSocket.

    Args:
        websocket: The incoming browser upgrade.
        upstream_path: The Hermes-side path to connect to
            (``/api/pty`` or ``/api/ws``).
    """
    user = resolve_websocket_user(websocket)
    # Accept first so the browser sees a meaningful close code rather
    # than a generic handshake failure.
    await websocket.accept()
    if user is None:
        await websocket.close(code=4401, reason="not_authenticated")
        return
    if not user.get("is_admin"):
        await websocket.close(code=4403, reason="forbidden")
        return

    manager = getattr(websocket.app.state, "hermes_manager", None)
    if manager is None:
        await websocket.close(code=4503, reason="hermes_disabled")
        return
    target = manager.resolve(user["id"])
    if target is None:
        await websocket.close(code=4503, reason="hermes_unavailable")
        return

    upstream_url = _build_upstream_url(
        target.ws_base_url,
        upstream_path,
        websocket.url.query,
        dict(websocket.query_params),
        target.token,
    )

    try:
        async with ws_connect(upstream_url, max_size=None) as upstream:
            await _pump(websocket, upstream)
    except (OSError, WebSocketException) as exc:
        _logger.warning("Hermes ws-proxy upstream error for %s: %s", upstream_path, exc)
        try:
            await websocket.close(code=1011, reason="upstream_error")
        except RuntimeError:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.websocket("/hermes/api/pty")
async def hermes_pty_ws(websocket: WebSocket) -> None:
    """Bridge the chat PTY WebSocket through to the Hermes dashboard."""
    await _proxy_ws(websocket, "/api/pty")


@router.websocket("/hermes/api/ws")
async def hermes_gateway_ws(websocket: WebSocket) -> None:
    """Bridge the dashboard gateway-event WebSocket through to Hermes."""
    await _proxy_ws(websocket, "/api/ws")
