"""Tests for the network (HTTP/SSE) transport of the catalog MCP server.

Covers the principal-scoping proxy, the auth ASGI wrapper (anonymous 401 +
per-principal binding), the settings gate, and that the SSE transport
actually streams for an authenticated caller — the integration-shell glue
that mounts the otherwise-stdio catalog MCP server on the web app.
"""

from __future__ import annotations

import types
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from pointlessql.api.catalog_mcp import (
    CATALOG_MCP_MOUNT,
    _active_uc,
    _principal_scoped_asgi,
    _PrincipalScopedUC,
    build_catalog_mcp_sse_app,
    mount_catalog_mcp,
)
from pointlessql.services.mcp_server import build_server


def _http_scope(
    state: dict[str, Any], *, path: str = "/sse", method: str = "GET"
) -> dict[str, Any]:
    """Build a minimal ASGI HTTP scope carrying *state* (the auth result)."""
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": [(b"host", b"pointlessql.example.com")],
        "query_string": b"",
        "scheme": "http",
        "client": ("203.0.113.7", 51234),
        "server": ("pointlessql.example.com", 443),
        "state": state,
        "root_path": "",
    }


async def _drive(app: Any, scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Run *app* against *scope* with a request-then-disconnect receive."""
    sent: list[dict[str, Any]] = []
    inbox = [
        {"type": "http.request", "body": b"", "more_body": False},
        {"type": "http.disconnect"},
    ]

    async def receive() -> dict[str, Any]:
        return inbox.pop(0) if inbox else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _authed_state(email: str = "alice@example.com") -> dict[str, Any]:
    """A request-state dict as the auth middleware would leave it for *email*."""
    return {
        "user": {
            "id": 1,
            "email": email,
            "display_name": "Alice",
            "is_admin": False,
            "is_supervisor": False,
            "is_auditor": False,
        }
    }


def _fake_app_with_client(principal: str, client: Any) -> Any:
    """A stand-in app whose state pre-caches *client* for *principal*.

    Pre-seeding the per-principal cache means the wrapper resolves the client
    from the cache and never constructs a real HTTP-backed facade.
    """
    state = types.SimpleNamespace(principal_uc_clients={principal: client})
    return types.SimpleNamespace(state=state)


class _FakeUC:
    """A facade stand-in recording dispatched tool calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def list_catalogs(self) -> list[dict[str, Any]]:
        self.calls.append("list_catalogs")
        return [{"name": "main"}]


def test_proxy_delegates_attribute_access_to_active_client() -> None:
    """The proxy forwards method lookups to the request's bound client."""
    fake = _FakeUC()
    token = _active_uc.set(fake)  # type: ignore[arg-type]
    try:
        proxy = _PrincipalScopedUC()
        assert proxy.list_catalogs == fake.list_catalogs
    finally:
        _active_uc.reset(token)


def test_proxy_without_active_client_raises() -> None:
    """A tool reaching the proxy outside an auth-scoped request fails loudly."""
    assert _active_uc.get() is None  # no request in flight
    with pytest.raises(RuntimeError, match="principal-scoped"):
        _PrincipalScopedUC().list_catalogs  # noqa: B018 — attribute access triggers __getattr__


@pytest.mark.asyncio
async def test_built_server_dispatches_through_the_scoped_proxy() -> None:
    """A tool call on a server built over the proxy reaches the bound client."""
    fake = _FakeUC()
    server = build_server(_PrincipalScopedUC(), name="t")  # type: ignore[arg-type]
    token = _active_uc.set(fake)  # type: ignore[arg-type]
    try:
        await server.call_tool("list_catalogs", {})
    finally:
        _active_uc.reset(token)
    assert fake.calls == ["list_catalogs"]


@pytest.mark.asyncio
async def test_wrapper_rejects_anonymous_with_401() -> None:
    """A request with no resolvable principal is refused before reaching inner."""
    reached = False

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        nonlocal reached
        reached = True

    wrapped = _principal_scoped_asgi(inner, _fake_app_with_client("x", object()))
    sent = await _drive(wrapped, _http_scope(state={}))  # anonymous: no user

    assert reached is False
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 401


@pytest.mark.asyncio
async def test_wrapper_binds_principal_client_and_resets_after() -> None:
    """An authenticated request runs inner with its principal's client bound."""
    fake = _FakeUC()
    captured: dict[str, Any] = {}

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        captured["uc"] = _active_uc.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = _principal_scoped_asgi(inner, _fake_app_with_client("alice@example.com", fake))
    await _drive(wrapped, _http_scope(state=_authed_state()))

    assert captured["uc"] is fake  # the caller's client was bound during the call
    assert _active_uc.get() is None  # and unbound once it returned


@pytest.mark.asyncio
async def test_wrapper_passes_non_http_scopes_through() -> None:
    """Lifespan (non-HTTP) scopes forward to inner without an auth check."""
    forwarded = False

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        nonlocal forwarded
        forwarded = True

    wrapped = _principal_scoped_asgi(inner, _fake_app_with_client("x", object()))

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(_message: dict[str, Any]) -> None:
        return None

    await wrapped({"type": "lifespan"}, receive, send)
    assert forwarded is True


@pytest.mark.asyncio
async def test_authenticated_sse_stream_opens() -> None:
    """The real SSE transport streams for an authenticated caller.

    Guards the disabled DNS-rebinding host pin: with FastMCP's localhost-only
    default still active a non-loopback Host would be rejected with 421.
    """
    fake = _FakeUC()
    sse_app = build_catalog_mcp_sse_app()
    wrapped = _principal_scoped_asgi(sse_app, _fake_app_with_client("alice@example.com", fake))

    sent = await _drive(wrapped, _http_scope(state=_authed_state()))

    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 200
    headers = {k.lower(): v for k, v in start["headers"]}
    assert headers[b"content-type"].startswith(b"text/event-stream")


def test_mount_is_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The network mount is omitted when the install disables it."""
    disabled = types.SimpleNamespace(catalog_mcp=types.SimpleNamespace(enabled=False))
    monkeypatch.setattr("pointlessql.config.get_settings", lambda: disabled)
    app = FastAPI()
    mount_catalog_mcp(app)
    assert not any(getattr(r, "path", None) == CATALOG_MCP_MOUNT for r in app.routes)


def test_mount_registers_the_endpoint_when_enabled() -> None:
    """With the default-enabled setting the SSE app is mounted at the path."""
    app = FastAPI()
    mount_catalog_mcp(app)
    assert any(getattr(r, "path", None) == CATALOG_MCP_MOUNT for r in app.routes)


def test_mounted_endpoint_requires_authentication() -> None:
    """End-to-end: an anonymous request to the mounted path is refused with 401."""
    app = FastAPI()

    @app.middleware("http")
    async def _fake_auth(request: Request, call_next: Any) -> Any:
        # Mirror the real auth middleware: set a user only when the test asks.
        if request.headers.get("x-test-user"):
            request.state.user = {  # type: ignore[assignment]
                "id": 1,
                "email": request.headers["x-test-user"],
                "display_name": "T",
                "is_admin": False,
                "is_supervisor": False,
                "is_auditor": False,
            }
        return await call_next(request)

    mount_catalog_mcp(app)
    with TestClient(app) as client:
        resp = client.get(f"{CATALOG_MCP_MOUNT}/sse")
    assert resp.status_code == 401
    assert "principal" in resp.json()["error"]


@pytest.mark.asyncio
async def test_real_app_middleware_returns_401_not_redirect_or_csrf(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Through the real middleware chain, an anonymous MCP request is a clean 401.

    Regression guard for the prefix wiring: without ``/catalog-mcp/`` in
    ``PUBLIC_PREFIXES`` the auth middleware would 303-redirect the GET to
    ``/auth/login`` (which a network MCP client never follows), and without
    the CSRF exemption the state-changing POST would be rejected with 403
    before either request ever reached the mount's own principal gate.
    """
    get_resp = await anonymous_client.get(f"{CATALOG_MCP_MOUNT}/sse")
    assert get_resp.status_code == 401  # not 303 (login redirect)

    post_resp = await anonymous_client.post(
        f"{CATALOG_MCP_MOUNT}/messages/",
        json={},
        headers={"content-type": "application/json"},
    )
    assert post_resp.status_code == 401  # not 403 (CSRF) and not 303
