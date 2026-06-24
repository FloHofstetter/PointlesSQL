"""Authenticating reverse-proxy in front of hosted-app workers.

App workers listen on loopback ports with no auth surface of their
own — every browser request goes through this proxy so PointlesSQL's
session cookie + ``UserInfo`` resolution gate applies before the
upstream call.  The shape mirrors :mod:`pointlessql.api.mlflow_proxy`
(buffered request/response forwarding, header strip on re-emission)
plus a WebSocket bridge for apps that stream (Streamlit's protocol
runs entirely over one WebSocket).

The proxy injects ``X-Forwarded-User`` (the operator's email) and
``X-Forwarded-Prefix`` (the public path the app is mounted under) so
prefix-aware frameworks can emit correct absolute URLs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from starlette.websockets import WebSocketDisconnect

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.api.ws_auth import resolve_websocket_user
from pointlessql.exceptions import AuthenticationError, ResourceNotFoundError
from pointlessql.models.hosted_apps import HostedApp
from pointlessql.services import app_hosting
from pointlessql.services.app_hosting import AppsManager
from pointlessql.services.workspace import _crud as workspaces_service
from pointlessql.types import UserInfo

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["apps-proxy"])

#: Close codes that only ever appear locally (no close frame / empty
#: close frame) — forwarding them on the wire is a protocol error, so
#: the bridge maps them to a normal closure.
_UNSENDABLE_CLOSE_CODES = frozenset({1005, 1006, 1015})


def _resolve_ready_app(request: Request, slug: str) -> tuple[HostedApp, AppsManager, int]:
    """Resolve the workspace's app and its live worker port.

    Args:
        request: Incoming FastAPI request.
        slug: App slug from the URL.

    Returns:
        ``(row, manager, port)`` for a ready app.

    Raises:
        ResourceNotFoundError: When the slug does not exist in the
            active workspace (foreign-workspace apps look absent on
            purpose).
        HTTPException: 503 when hosted apps are not wired, the app
            is not in ``ready`` state, or no worker port is live.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = app_hosting.get_app(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"App '{slug}' not found.")
    if row.state != "ready":
        # bare-http-ok: 503 is the canonical not-ready status; no
        # domain-named exception exists for it.
        raise HTTPException(
            status_code=503,
            detail=f"App '{slug}' is not ready (state: {row.state}).",
        )
    manager: AppsManager | None = getattr(request.app.state, "apps_manager", None)
    if manager is None:
        # bare-http-ok: 503 is the canonical subsystem-not-wired
        # status; no domain-named exception exists for it.
        raise HTTPException(status_code=503, detail="hosted apps are not enabled")
    port = manager.port_for(row.id)
    if port is None:
        # bare-http-ok: 503 is the canonical worker-not-live status;
        # no domain-named exception exists for it.
        raise HTTPException(
            status_code=503,
            detail=f"App '{slug}' has no live worker — start it first.",
        )
    return row, manager, port


@router.api_route(
    "/apps/{slug}/proxy/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"],
    # Explicit because FastAPI's default unique-id picks an arbitrary
    # member of the methods *set*, which made the generated OpenAPI
    # snapshot flip between runs.
    operation_id="apps_proxy_apps_slug_proxy_path",
)
async def apps_proxy(slug: str, path: str, request: Request) -> Response:
    """Forward an authenticated request to the app's worker.

    Args:
        slug: App slug — selects the worker.
        path: Captured path segment after ``/apps/<slug>/proxy/`` —
            empty for the app root, asset paths and API routes
            otherwise.
        request: The incoming FastAPI request (used for method,
            body, query-string, and auth-state).

    Returns:
        Response: The upstream response with content + status + safe
            headers preserved.  Anonymous callers get a 401 instead.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
        HTTPException: 502 on upstream HTTP error from the worker.
    """
    user: UserInfo = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("Auth required for hosted apps")

    row, manager, port = _resolve_ready_app(request, slug)

    target_url = f"http://127.0.0.1:{port}/{path}"
    upstream_headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    upstream_headers["X-Forwarded-User"] = user["email"]
    upstream_headers["X-Forwarded-Prefix"] = f"/apps/{row.slug}/proxy"

    body = await request.body()

    # Tests may install a ``httpx.MockTransport`` on
    # ``app.state.apps_proxy_transport`` to assert proxy behaviour
    # without spawning a real worker.
    transport = getattr(request.app.state, "apps_proxy_transport", None)
    timeout = manager.config.request_timeout_seconds

    if transport is None:
        client = httpx.AsyncClient(timeout=timeout)
    else:
        client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async with client:
        try:
            upstream = await client.request(
                request.method,
                target_url,
                params=request.query_params,
                content=body,
                headers=upstream_headers,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            # logger.exception captures the traceback — several httpx
            # transport errors (ConnectError/ReadTimeout) stringify empty.
            _logger.exception("hosted-app proxy upstream error for %s/%s", slug, path)
            # bare-http-ok: 502 is the canonical proxy-upstream-failed
            # status; no domain-named exception exists for it.  The detail
            # stays generic so the upstream host:port in ``exc`` is not
            # disclosed to the client.
            raise HTTPException(status_code=502, detail="App upstream is unavailable") from exc

    # Strip headers that interfere with our re-emission.
    # ``content-encoding`` would force the client to decode an
    # already-decoded body (httpx auto-decompresses);
    # ``content-length`` is set by Starlette based on the body we
    # hand it.
    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
    }

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


def _sendable_close_code(code: int | None) -> int:
    """Map a received close code to one that is legal to send."""
    if code is None or code in _UNSENDABLE_CLOSE_CODES:
        return 1000
    return code


async def _pump_client_to_upstream(websocket: WebSocket, upstream: Any) -> None:
    """Forward browser frames to the worker until either side closes.

    Args:
        websocket: The accepted browser-side socket.
        upstream: The ``websockets`` client connection.
    """
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            await upstream.close(code=_sendable_close_code(message.get("code")))
            return
        text = message.get("text")
        if text is not None:
            await upstream.send(text)
            continue
        data = message.get("bytes")
        if data is not None:
            await upstream.send(data)


async def _pump_upstream_to_client(websocket: WebSocket, upstream: Any) -> None:
    """Forward worker frames to the browser, then mirror the close.

    Args:
        websocket: The accepted browser-side socket.
        upstream: The ``websockets`` client connection.
    """
    import websockets

    try:
        async for frame in upstream:
            if isinstance(frame, str):
                await websocket.send_text(frame)
            else:
                await websocket.send_bytes(frame)
    except websockets.exceptions.ConnectionClosed:
        pass
    await websocket.close(
        code=_sendable_close_code(upstream.close_code),
        reason=upstream.close_reason or "",
    )


@router.websocket("/apps/{slug}/proxy/{path:path}")
async def apps_proxy_ws(websocket: WebSocket, slug: str, path: str) -> None:
    """Bridge a browser WebSocket to the app worker's WebSocket.

    Auth mirrors the HTTP proxy: the cookie user resolves before the
    upgrade is accepted (Bearer keys are refused like anonymous —
    apps are a browser surface).  Close codes:

    - 4401 — unauthenticated.
    - 4404 — unknown slug in the caller's workspace.
    - 4503 — hosted apps not wired / app not ready / worker dead.
    - 1011 — the optional ``websockets`` package is missing or the
      upstream connect failed.

    Args:
        websocket: The incoming WebSocket connection.
        slug: App slug — selects the worker.
        path: Captured path after ``/apps/<slug>/proxy/``.
    """
    user = resolve_websocket_user(websocket)
    if user is None or int(user.get("id") or 0) == 0:
        await websocket.close(code=4401)
        return
    factory = getattr(websocket.app.state, "session_factory", None)
    if factory is None:
        await websocket.close(code=4503)
        return
    workspace_id, _source = workspaces_service.resolve_workspace_id(
        factory,
        user_id=int(user.get("id") or 0) or None,
        header_value=websocket.headers.get("x-workspace"),
    )
    row = app_hosting.get_app(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        await websocket.close(code=4404)
        return
    manager: AppsManager | None = getattr(websocket.app.state, "apps_manager", None)
    port = manager.port_for(row.id) if manager is not None else None
    if row.state != "ready" or port is None:
        await websocket.close(code=4503)
        return

    await websocket.accept()
    try:
        import websockets
    except ImportError:
        await websocket.close(code=1011, reason="websockets library is not installed")
        return

    query = websocket.url.query
    target = f"ws://127.0.0.1:{port}/{path}" + (f"?{query}" if query else "")
    try:
        upstream = await websockets.connect(
            target,
            additional_headers={
                "X-Forwarded-User": str(user.get("email") or ""),
                "X-Forwarded-Prefix": f"/apps/{row.slug}/proxy",
            },
        )
    except OSError as exc:
        _logger.warning("hosted-app WS upstream connect failed for %s/%s: %s", slug, path, exc)
        await websocket.close(code=1011, reason="app worker refused the WebSocket")
        return

    client_task = asyncio.create_task(_pump_client_to_upstream(websocket, upstream))
    upstream_task = asyncio.create_task(_pump_upstream_to_client(websocket, upstream))
    try:
        _done, pending = await asyncio.wait(
            {client_task, upstream_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    finally:
        client_task.cancel()
        upstream_task.cancel()
        await asyncio.gather(client_task, upstream_task, return_exceptions=True)
        await upstream.close()
