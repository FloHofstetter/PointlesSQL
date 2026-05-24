"""Tests for :func:`pointlessql.services.workspace._crud.resolve_workspace_id`.

The resolver is the non-HTTP entry point that the auth middleware,
the scheduler tick loop, the CLI, and test fixtures all share.
The cases below pin the priority order:

    X-Workspace header > API-key pin > session cookie > user.default > 1

plus the safety guarantees (never raises, always returns a positive
int, falls through silently on lookup failure).
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AuditLog, User
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        user = session.query(User).filter(User.email == "test@test.com").one()
        return user.id


def test_resolver_falls_through_to_default_floor_when_nothing_supplied() -> None:
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=None,
        header_value=None,
        cookie_value=None,
        api_key_workspace_id=None,
    )
    assert workspace_id == 1
    assert source == "fallback"


def test_resolver_uses_user_default_when_only_user_id_supplied() -> None:
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=_admin_user_id(),
        header_value=None,
        cookie_value=None,
        api_key_workspace_id=None,
    )
    assert workspace_id == 1
    assert source == "user_default"


def test_resolver_uses_api_key_pin_over_user_default() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="api-key-ws", name="x")
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=None,
        header_value=None,
        cookie_value=None,
        api_key_workspace_id=ws.id,
    )
    assert workspace_id == ws.id
    assert source == "api_key"


def test_resolver_uses_cookie_when_no_header_and_no_api_key() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="cookie-ws", name="x")
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=_admin_user_id(),
        header_value=None,
        cookie_value="cookie-ws",
        api_key_workspace_id=None,
    )
    assert workspace_id == ws.id
    assert source == "cookie"


def test_resolver_header_wins_over_cookie_and_api_key() -> None:
    a = workspaces_service.create_workspace(_factory(), slug="header-ws", name="A")
    b = workspaces_service.create_workspace(_factory(), slug="other-ws", name="B")
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=_admin_user_id(),
        header_value="header-ws",
        cookie_value="other-ws",
        api_key_workspace_id=b.id,
    )
    assert workspace_id == a.id
    assert source == "header"


def test_resolver_returns_default_for_unknown_header_slug() -> None:
    """Unknown header slugs degrade silently to the next priority tier."""
    workspace_id, source = workspaces_service.resolve_workspace_id(
        _factory(),
        user_id=_admin_user_id(),
        header_value="does-not-exist",
        cookie_value=None,
        api_key_workspace_id=None,
    )
    assert workspace_id == 1
    assert source == "user_default"


def test_resolver_tolerates_missing_factory() -> None:
    """A None factory must not raise — used by deployment-time edge cases."""
    workspace_id, source = workspaces_service.resolve_workspace_id(
        None,
        user_id=42,
        header_value="anything",
        cookie_value=None,
        api_key_workspace_id=None,
    )
    assert workspace_id == 1
    assert source == "fallback"


# ---------------------------------------------------------------------------
# Middleware integration — header-driven mismatch path
# ---------------------------------------------------------------------------


def _wipe_api_keys() -> None:
    factory = _factory()
    with factory() as session:
        from pointlessql.models import ApiKey

        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.mark.asyncio
async def test_middleware_attaches_workspace_id_for_cookie_user() -> None:
    """Browser session ends up at workspace_id=1 via user.default."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/api/agent-runs/recent?limit=1")
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_middleware_403s_user_requesting_unjoined_workspace() -> None:
    """X-Workspace pointing to a workspace the user does NOT belong to is 403."""
    workspaces_service.create_workspace(_factory(), slug="forbidden-ws", name="x")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(
            "/api/agent-runs/recent?limit=1",
            headers={"X-Workspace": "forbidden-ws"},
        )
    assert response.status_code == 403
    body = response.json()
    # middleware emits RFC 9457 problem+json now.
    assert body["status"] == 403
    assert body["code"] == "workspace_context_mismatch"
    assert "workspace" in body["detail"].lower()

    # The mismatch must surface as an audit_log row.
    with _factory()() as session:
        rows = session.query(AuditLog).filter(AuditLog.action == "workspace.context_mismatch").all()
        assert len(rows) >= 1
        assert any("forbidden-ws" in r.target for r in rows)


@pytest.mark.asyncio
async def test_middleware_allows_member_to_use_workspace_via_header() -> None:
    """X-Workspace pointing to a workspace the user IS a member of passes."""
    factory = _factory()
    ws = workspaces_service.create_workspace(factory, slug="allowed-ws", name="x")
    workspaces_service.add_member(
        factory, workspace_id=ws.id, user_id=_admin_user_id(), role="member"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(
            "/api/agent-runs/recent?limit=1",
            headers={"X-Workspace": "allowed-ws"},
        )
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_middleware_403s_api_key_with_mismatched_header() -> None:
    """An api_key pinned to ws=1 cannot drive a request against ws=other."""
    factory = _factory()
    other = workspaces_service.create_workspace(factory, slug="other-ws-2", name="x")
    _wipe_api_keys()
    try:
        _, plaintext = api_keys_service.create_api_key(
            factory, name="ws_pin_test", auditor=True, workspace_id=1
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/agent-runs/recent?limit=1",
                headers={
                    "Authorization": f"Bearer {plaintext}",
                    "X-Workspace": "other-ws-2",
                },
            )
        assert response.status_code == 403
        # middleware emits RFC 9457 problem+json now.
        body = response.json()
        assert body["status"] == 403
        assert body["code"] == "workspace_context_mismatch"
    finally:
        _wipe_api_keys()
        # Use `other` so pyright/ruff don't complain about unused.
        assert other.slug == "other-ws-2"
