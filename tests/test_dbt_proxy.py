"""Tests for the dbt-docs reverse-proxy.

Mocks the upstream dbt-docs subprocess via ``httpx.MockTransport`` so
auth-gating + header injection can be asserted without spawning a
real ``dbt docs serve`` server.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from pointlessql.api.main import app


@pytest.fixture
def mock_upstream() -> Iterator[dict[str, Any]]:
    """Install an ``httpx.MockTransport`` for the proxy's upstream call.

    The proxy reads ``app.state.dbt_proxy_transport`` and routes its
    outbound httpx call through it when set, leaving the FastAPI test
    client's ASGI transport free to actually run the route.
    """
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            content=b"<html>dbt-docs</html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(_handler)
    app.state.dbt_proxy_transport = transport
    try:
        yield captured
    finally:
        app.state.dbt_proxy_transport = None


def test_anonymous_request_redirects_to_login() -> None:
    """No auth cookie → 303 (auth middleware fires before the proxy)."""
    with TestClient(app, follow_redirects=False) as client:
        resp = client.get("/dbt-docs/manifest.json")
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_subprocess_not_running_returns_503(auth_cookies: dict[str, str]) -> None:
    """Auth'd request but app.state.dbt_subprocess is None → 503."""
    transport = httpx.ASGITransport(app=app)
    app.state.dbt_subprocess = None
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get("/dbt-docs/manifest.json")
    assert resp.status_code == 503
    assert "dbt-docs subprocess is not running" in resp.text


@pytest.mark.asyncio
async def test_authenticated_request_proxies_and_injects_user_header(
    auth_cookies: dict[str, str],
    mock_upstream: dict[str, Any],
) -> None:
    """Auth'd request forwards method, path, and X-DBT-User header."""

    class _StubProc:
        pass

    app.state.dbt_subprocess = _StubProc()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/dbt-docs/manifest.json")
    finally:
        app.state.dbt_subprocess = None

    assert resp.status_code == 200
    assert resp.text == "<html>dbt-docs</html>"
    assert mock_upstream["method"] == "GET"
    assert mock_upstream["url"].endswith("/manifest.json")
    headers_lower = {k.lower(): v for k, v in mock_upstream["headers"].items()}
    assert headers_lower.get("x-dbt-user") == "test@test.com"
    assert mock_upstream["headers"].get("host", "").startswith("127.0.0.1")


@pytest.mark.asyncio
async def test_dbt_page_renders_install_hint_when_subprocess_off(
    auth_cookies: dict[str, str],
) -> None:
    """The /dbt page renders the warning banner when the subprocess is off."""
    app.state.dbt_subprocess = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get("/dbt")
    assert resp.status_code == 200
    assert "dbt-docs not running" in resp.text
    assert "pip install pointlessql[dbt]" in resp.text


@pytest.mark.asyncio
async def test_dbt_page_redirects_anonymous_to_login() -> None:
    """Anonymous /dbt request lands on the login redirect."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", follow_redirects=False
    ) as c:
        resp = await c.get("/dbt")
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers.get("location", "")
