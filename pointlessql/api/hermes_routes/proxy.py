"""Reverse-proxy for the embedded Hermes agent dashboard.

The PointlesSQL "Agent" tab embeds the Hermes web dashboard in an
iframe at ``/hermes/``.  The dashboard listens on its own port (a
managed subprocess or an external host) and gates ``/api/*`` with a
pre-shared token, so every request flows through this proxy: it
applies PointlesSQL's own admin gate first, then forwards under the
Hermes session token.

Two header rules make the upstream SPA resolve correctly:

- ``X-Forwarded-Prefix: /hermes`` — Hermes is built to be served
  behind a path prefix; this makes the served HTML + CSS rewrite all
  asset and API URLs under ``/hermes`` so the iframe loads same-origin.
- the inbound ``X-Forwarded-For`` is dropped — Hermes treats a
  forwarded client IP as the real peer, which would defeat its
  loopback-only WebSocket gate for the chat pane.

Streaming: this proxy buffers full request + response bodies, which is
fine for the SPA bundle + JSON API traffic.  The chat PTY is a
WebSocket and is handled separately by the ws-proxy router, not here.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.services.hermes import HermesStartupError
from pointlessql.types import UserInfo

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["hermes"])

_PROXY_TIMEOUT_S = 300.0
_HOP_BY_HOP_RESPONSE = {"content-encoding", "content-length", "transfer-encoding"}
_DROP_REQUEST_HEADERS = {"host", "x-forwarded-for"}


@router.api_route("/hermes", methods=["GET", "HEAD"], include_in_schema=False)
async def hermes_root_redirect() -> RedirectResponse:
    """Redirect the bare ``/hermes`` to ``/hermes/`` so the SPA loads."""
    return RedirectResponse(url="/hermes/", status_code=307)


@router.api_route(
    "/hermes/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"],
    # Explicit because FastAPI's default unique-id picks an arbitrary
    # member of the methods *set*, which made the generated OpenAPI
    # snapshot flip between runs.
    operation_id="hermes_proxy_hermes_path",
)
async def hermes_proxy(path: str, request: Request) -> Response:
    """Forward an admin request to the Hermes dashboard.

    Args:
        path: Captured path after ``/hermes/`` — empty for the SPA
            root, ``assets/...`` for the bundle, ``api/...`` for the
            dashboard's own REST surface.
        request: The incoming request (method, body, query, auth).

    Returns:
        Response: The upstream response with content + status + safe
            headers preserved.

    Raises:
        HermesStartupError: 503 when Hermes is not enabled or no
            managed instance is running.
        HTTPException: 502 on an upstream HTTP error.
    """
    # ``require_admin`` raises ``AuthorizationError`` (403) for non-admins.
    require_admin(request)
    user: UserInfo = get_user(request)

    manager = getattr(request.app.state, "hermes_manager", None)
    if manager is None:
        raise HermesStartupError(
            "Hermes is not enabled. Set POINTLESSQL_HERMES_ENABLED=1.",
        )
    target = manager.resolve(user["id"])
    if target is None:
        raise HermesStartupError(
            "Hermes dashboard is not running. Check the managed-launch logs "
            "or point POINTLESSQL_HERMES_DASHBOARD_URL at an external instance.",
        )

    target_url = f"{target.base_url}/{path}"
    upstream_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQUEST_HEADERS
    }
    upstream_headers["X-Forwarded-Prefix"] = "/hermes"
    if target.token:
        upstream_headers["X-Hermes-Session-Token"] = target.token

    body = await request.body()

    # Tests install an ``httpx.MockTransport`` on
    # ``app.state.hermes_proxy_transport`` to assert proxy behaviour
    # without spawning a real Hermes dashboard.
    transport = getattr(request.app.state, "hermes_proxy_transport", None)
    client = (
        httpx.AsyncClient(timeout=_PROXY_TIMEOUT_S, transport=transport)
        if transport is not None
        else httpx.AsyncClient(timeout=_PROXY_TIMEOUT_S)
    )

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
            _logger.warning("Hermes proxy upstream error for %s: %s", path, exc)
            # bare-http-ok: 502 is the canonical proxy-upstream-failed
            # status; no domain-named exception exists for it.
            raise HTTPException(status_code=502, detail=f"Hermes upstream error: {exc}") from exc

    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP_RESPONSE
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
