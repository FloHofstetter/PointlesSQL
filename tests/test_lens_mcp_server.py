"""Sprint 65.4 — MCP server bindings tests.

Cover the in-process FastMCP construction + auth resolution + the
SSE wrapper.  The actual stdio handshake is exercised by the
walkthrough in 65.7; here we keep the test cheap by inspecting the
constructed FastMCP and the route surfaces.
"""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.api_keys import (
    create_api_key,
    invalidate_cache,
    revoke_api_key,
)
from pointlessql.services.lens.mcp_server import (
    LensMcpAuthError,
    create_lens_mcp_server,
    resolve_lens_key,
)


def _ensure_keys_table() -> None:
    """Wipe + invalidate so each test starts with a clean api_keys cache."""
    factory = app.state.session_factory
    from pointlessql.models import ApiKey

    with factory() as s:
        s.query(ApiKey).delete()
        s.commit()
    invalidate_cache()


def _mint_key(*, name: str, **scopes: bool) -> str:
    """Create + return the plaintext for a fresh key."""
    factory = app.state.session_factory
    _, secret = create_api_key(factory, name=name, **scopes)
    return secret


def test_resolve_lens_key_accepts_analyst_scope() -> None:
    """Analyst-flagged key resolves to a usable KeyEntry."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-1", analyst=True)
    factory = app.state.session_factory
    entry = resolve_lens_key(factory, bearer_value=secret)
    assert entry.analyst is True
    assert entry.workspace_id == 1


def test_resolve_lens_key_accepts_auditor_scope() -> None:
    """Auditor-only key passes (auditor is a Lens superset)."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-2", auditor=True)
    factory = app.state.session_factory
    entry = resolve_lens_key(factory, bearer_value=secret)
    assert entry.auditor is True


def test_resolve_lens_key_refuses_supervisor_only() -> None:
    """A supervisor-only key (no analyst/auditor) is rejected."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-3", supervisor=True)
    factory = app.state.session_factory
    with pytest.raises(LensMcpAuthError):
        resolve_lens_key(factory, bearer_value=secret)


def test_resolve_lens_key_missing_bearer_raises() -> None:
    """No bearer at all → LensMcpAuthError."""
    factory = app.state.session_factory
    with pytest.raises(LensMcpAuthError):
        resolve_lens_key(factory, bearer_value=None)


def test_resolve_lens_key_revoked_raises() -> None:
    """Revoked keys do not resolve."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-4", analyst=True)
    factory = app.state.session_factory
    revoke_api_key(factory, name="lens-mcp-test-4")
    invalidate_cache()
    with pytest.raises(LensMcpAuthError):
        resolve_lens_key(factory, bearer_value=secret)


def test_create_lens_mcp_server_registers_every_tool() -> None:
    """The constructed FastMCP carries one tool per ALL_TOOLS entry."""
    from pointlessql.config import Settings
    from pointlessql.services.lens.tools import ALL_TOOLS

    factory = app.state.session_factory
    settings = Settings()
    mcp = create_lens_mcp_server(
        factory=factory, settings=settings, api_key_secret=None
    )
    # FastMCP exposes _tool_manager._tools as the registry; this is
    # an internal but stable attr in the 1.x line.  We walk it
    # rather than hit the network.
    registered = list(mcp._tool_manager._tools.keys())  # noqa: SLF001 — test inspection
    expected = {tool.name for tool in ALL_TOOLS}
    assert expected <= set(registered)


def test_create_lens_mcp_server_with_api_key_resolves_workspace() -> None:
    """Pre-resolving a Bearer caches the workspace context."""
    from pointlessql.config import Settings

    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-5", analyst=True)
    factory = app.state.session_factory
    settings = Settings()
    # Should not raise.
    create_lens_mcp_server(
        factory=factory, settings=settings, api_key_secret=secret
    )


@pytest.mark.asyncio
async def test_mcp_health_route(admin_client: httpx.AsyncClient) -> None:
    """GET /mcp/health returns ok + tool count."""
    resp = await admin_client.get("/mcp/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["tools"] >= 6  # ALL_TOOLS has at least 6


@pytest.mark.asyncio
async def test_mcp_info_unauthenticated_returns_403(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """No Bearer → /mcp/info returns 403 with explanatory body."""
    resp = await anonymous_client.get("/mcp/info")
    assert resp.status_code == 403
    body = resp.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_mcp_info_with_analyst_key_echoes_workspace(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Analyst-keyed call echoes workspace_id + scope list."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-info", analyst=True)
    headers = {"Authorization": f"Bearer {secret}"}
    resp = await anonymous_client.get("/mcp/info", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == 1
    assert "analyst" in body["scopes"]


@pytest.mark.asyncio
async def test_mcp_info_with_revoked_key_rejected(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Revoked key → 403 even though hash matches."""
    _ensure_keys_table()
    secret = _mint_key(name="lens-mcp-test-revoked", analyst=True)
    factory = app.state.session_factory
    revoke_api_key(factory, name="lens-mcp-test-revoked")
    invalidate_cache()
    headers = {"Authorization": f"Bearer {secret}"}
    resp = await anonymous_client.get("/mcp/info", headers=headers)
    assert resp.status_code == 403


def test_now_helper_callable() -> None:
    """Sanity guard so the test file imports cleanly under pytest."""
    assert isinstance(datetime.datetime.now(datetime.UTC), datetime.datetime)
