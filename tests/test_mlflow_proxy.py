"""Tests for the MLflow reverse-proxy (Phase 21.0).

Mocks the upstream MLflow subprocess via ``httpx.MockTransport`` so we
can assert auth-gating and header injection without spawning a real
server.
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

    The proxy reads ``app.state.mlflow_proxy_transport`` and routes
    its outbound httpx call through it when set. Patching the
    transport (rather than ``httpx.AsyncClient.send`` globally)
    leaves the test client's ASGI transport alone, so the proxy
    route actually runs.
    """
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            content=b'{"mlflow":"ok"}',
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(_handler)
    app.state.mlflow_proxy_transport = transport
    try:
        yield captured
    finally:
        app.state.mlflow_proxy_transport = None


def test_anonymous_request_redirects_to_login() -> None:
    """No auth cookie → 303 redirect (auth middleware fires first)."""
    with TestClient(app, follow_redirects=False) as client:
        resp = client.get("/mlflow/api/2.0/mlflow/experiments/list")
        assert resp.status_code == 303
        assert "/auth/login" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_subprocess_not_running_returns_503(auth_cookies: dict[str, str]) -> None:
    """Auth'd request but app.state.mlflow_subprocess is None → 503."""
    transport = httpx.ASGITransport(app=app)
    app.state.mlflow_subprocess = None
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get("/mlflow/api/2.0/mlflow/experiments/list")
    assert resp.status_code == 503
    assert "MLflow subprocess is not running" in resp.text


@pytest.mark.asyncio
async def test_authenticated_request_proxies_and_injects_user_header(
    auth_cookies: dict[str, str],
    mock_upstream: dict[str, Any],
) -> None:
    """Auth'd request forwards method, path, and X-MLflow-User."""

    class _StubProc:
        pass

    app.state.mlflow_subprocess = _StubProc()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/mlflow/api/2.0/mlflow/experiments/list")
    finally:
        app.state.mlflow_subprocess = None

    assert resp.status_code == 200
    assert resp.json() == {"mlflow": "ok"}
    assert mock_upstream["method"] == "GET"
    assert mock_upstream["url"].endswith("/api/2.0/mlflow/experiments/list")
    # Auth-derived header injection.
    # httpx stores headers case-insensitively (HTTP spec); compare lowercased.
    headers_lower = {k.lower(): v for k, v in mock_upstream["headers"].items()}
    assert headers_lower.get("x-mlflow-user") == "test@test.com"
    # The incoming "Host: testserver" was stripped — the upstream Host header
    # is the MLflow target (127.0.0.1:port), set by httpx itself.
    assert mock_upstream["headers"].get("host", "").startswith("127.0.0.1")
