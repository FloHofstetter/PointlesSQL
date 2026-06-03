"""Tests for the embedded Hermes agent dashboard integration.

Covers the settings submodel, the instance manager's resolve logic
(external + managed), and the reverse-proxy router's admin gate +
header injection.  The upstream Hermes dashboard is mocked via
``httpx.MockTransport`` so nothing is spawned.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from pointlessql.api.main import app
from pointlessql.config import HermesSettings
from pointlessql.services.hermes import HermesInstance, HermesInstanceManager


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def test_hermes_settings_defaults() -> None:
    """The Agent integration is opt-in and loopback-managed by default."""
    s = HermesSettings()
    assert s.enabled is False
    assert s.mode == "managed"
    assert s.isolation == "shared"
    assert s.dashboard_url == "http://127.0.0.1:9119"
    assert s.host == "127.0.0.1"
    assert s.port_base == 9119
    assert s.chat_enabled is True
    assert s.acp_enabled is False


# --------------------------------------------------------------------------- #
# Manager.resolve
# --------------------------------------------------------------------------- #
def test_manager_resolve_external() -> None:
    """External mode resolves to the configured URL + derived ws base."""
    mgr = HermesInstanceManager(
        HermesSettings(mode="external", dashboard_url="http://hermes:9119", session_token="tok")
    )
    target = mgr.resolve()
    assert target is not None
    assert target.base_url == "http://hermes:9119"
    assert target.ws_base_url == "ws://hermes:9119"
    assert target.token == "tok"
    assert target.instance is None


def test_manager_resolve_managed_not_started() -> None:
    """Managed mode with no running instance resolves to None (→ 503)."""
    mgr = HermesInstanceManager(HermesSettings(mode="managed"))
    assert mgr.resolve() is None


@pytest.mark.asyncio
async def test_manager_resolve_shared_after_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """After ``start_shared`` the shared instance is resolvable with its token."""

    async def _fake_start(self: HermesInstance) -> None:
        self.proc = object()  # pretend the process is alive

    monkeypatch.setattr(HermesInstance, "start", _fake_start)
    mgr = HermesInstanceManager(
        HermesSettings(mode="managed", session_token="shared-tok", port_base=9119)
    )
    await mgr.start_shared()
    target = mgr.resolve()
    assert target is not None
    assert target.base_url == "http://127.0.0.1:9119"
    assert target.token == "shared-tok"
    assert target.instance is not None


# --------------------------------------------------------------------------- #
# Reverse proxy
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_upstream() -> Iterator[dict[str, Any]]:
    """Install an ``httpx.MockTransport`` for the proxy's upstream call."""
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200, content=b"<html>hermes</html>", headers={"content-type": "text/html"}
        )

    transport = httpx.MockTransport(_handler)
    app.state.hermes_proxy_transport = transport
    try:
        yield captured
    finally:
        app.state.hermes_proxy_transport = None


def test_anonymous_request_redirects_to_login() -> None:
    """No auth cookie → 303 redirect (auth middleware fires first)."""
    with TestClient(app, follow_redirects=False) as client:
        resp = client.get("/hermes/api/status")
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_non_admin_forbidden(non_admin_cookies: dict[str, str]) -> None:
    """An authenticated non-admin is rejected (the agent can run commands)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=non_admin_cookies
    ) as c:
        resp = await c.get("/hermes/")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_not_enabled_returns_503(auth_cookies: dict[str, str]) -> None:
    """Admin request but no manager configured → 503."""
    prev = getattr(app.state, "hermes_manager", None)
    app.state.hermes_manager = None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/hermes/")
    finally:
        app.state.hermes_manager = prev
    assert resp.status_code == 503
    assert "Hermes is not enabled" in resp.text


@pytest.mark.asyncio
async def test_proxy_injects_prefix_and_token_and_drops_forwarded_for(
    auth_cookies: dict[str, str],
    mock_upstream: dict[str, Any],
) -> None:
    """Forwards under the path prefix + session token; drops X-Forwarded-For."""
    prev = getattr(app.state, "hermes_manager", None)
    app.state.hermes_manager = HermesInstanceManager(
        HermesSettings(mode="external", dashboard_url="http://hermes:9119", session_token="tok")
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/hermes/assets/app.js", headers={"X-Forwarded-For": "1.2.3.4"})
    finally:
        app.state.hermes_manager = prev

    assert resp.status_code == 200
    assert mock_upstream["method"] == "GET"
    assert mock_upstream["url"] == "http://hermes:9119/assets/app.js"
    headers_lower = {k.lower(): v for k, v in mock_upstream["headers"].items()}
    assert headers_lower.get("x-forwarded-prefix") == "/hermes"
    assert headers_lower.get("x-hermes-session-token") == "tok"
    # The loopback WebSocket gate would be defeated by a forwarded client IP.
    assert "x-forwarded-for" not in headers_lower
    # Inbound Host stripped → httpx sets it from the upstream target.
    assert headers_lower.get("host", "").startswith("hermes")


# --------------------------------------------------------------------------- #
# Status endpoint
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_status_endpoint_disabled(auth_cookies: dict[str, str]) -> None:
    """Status with no manager reports a disabled snapshot."""
    prev = getattr(app.state, "hermes_manager", None)
    app.state.hermes_manager = None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/api/hermes/status")
    finally:
        app.state.hermes_manager = prev
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_status_endpoint_non_admin_forbidden(non_admin_cookies: dict[str, str]) -> None:
    """Status is admin-only."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=non_admin_cookies
    ) as c:
        resp = await c.get("/api/hermes/status")
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Chat WebSocket proxy
# --------------------------------------------------------------------------- #
def test_build_upstream_url_forwards_query_and_token_fallback() -> None:
    """The browser's auth query is forwarded; token fills in only when absent."""
    from pointlessql.api.hermes_routes.ws_proxy import _build_upstream_url

    # SPA already sent a token → forward verbatim, no double-append.
    assert (
        _build_upstream_url("ws://h:9119", "/api/pty", "token=abc", {"token": "abc"}, "xyz")
        == "ws://h:9119/api/pty?token=abc"
    )
    # Gated ticket present → never inject a token.
    assert (
        _build_upstream_url("ws://h:9119", "/api/pty", "ticket=t1", {"ticket": "t1"}, "xyz")
        == "ws://h:9119/api/pty?ticket=t1"
    )
    # No client credential → fall back to the instance token.
    assert (
        _build_upstream_url("ws://h:9119", "/api/pty", "", {}, "xyz")
        == "ws://h:9119/api/pty?token=xyz"
    )
    # No credential anywhere → bare path.
    assert _build_upstream_url("ws://h:9119", "/api/ws", "", {}, None) == "ws://h:9119/api/ws"


def test_ws_proxy_anonymous_closes_4401() -> None:
    """An unauthenticated chat upgrade is accepted then closed 4401."""
    from starlette.websockets import WebSocketDisconnect as _WSD

    with TestClient(app) as client:
        with pytest.raises(_WSD) as exc:
            with client.websocket_connect("/hermes/api/pty") as ws:
                ws.receive_text()
        assert exc.value.code == 4401


@pytest.mark.asyncio
async def test_ws_proxy_non_admin_closes_4403(non_admin_cookies: dict[str, str]) -> None:
    """A non-admin chat upgrade is closed 4403 (the agent can run commands)."""
    from starlette.websockets import WebSocketDisconnect as _WSD

    with TestClient(app, cookies=non_admin_cookies) as client:
        with pytest.raises(_WSD) as exc:
            with client.websocket_connect("/hermes/api/pty") as ws:
                ws.receive_text()
        assert exc.value.code == 4403
