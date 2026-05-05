"""Tests for the Bearer-token API-key gate.

Originally Sprint 13.7.0.5 (env-var-based store).  Sprint 13.11.4a
promoted the store to a real DB table; this file was rewritten in
the same sprint so the env-var format extension and the DB-backed
verify path are both covered.

The bootstrap path (``bootstrap_from_env``) keeps the historical
``POINTLESSQL_API_KEYS`` env var valid as a clean-machine auth
seed.  The HTTP integration cases below provision keys with the
:func:`create_api_key` helper, exercising the same write surface
that the admin CRUD route uses.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import ApiKey, AuditLog
from pointlessql.services import api_keys as api_keys_service

# ---------------------------------------------------------------------------
# parse_keys (pure function, no HTTP / no DB)
# ---------------------------------------------------------------------------


def test_parse_keys_empty_returns_empty_mapping() -> None:
    assert api_keys_service.parse_keys(None) == {}
    assert api_keys_service.parse_keys("") == {}
    assert api_keys_service.parse_keys("   \n\n  ") == {}


def test_parse_keys_supports_newline_and_comma() -> None:
    raw = "hermes:abc123\npaperclip:xyz789, bot:secret"
    parsed = api_keys_service.parse_keys(raw)
    assert parsed == {
        "hermes": ("abc123", False, False),
        "paperclip": ("xyz789", False, False),
        "bot": ("secret", False, False),
    }


def test_parse_keys_supports_supervisor_scope() -> None:
    raw = "alice:s1, sup:godkey:supervisor"
    parsed = api_keys_service.parse_keys(raw)
    assert parsed == {
        "alice": ("s1", False, False),
        "sup": ("godkey", True, False),
    }


def test_parse_keys_supports_auditor_scope() -> None:
    raw = "alice:s1, aud:k:auditor"
    parsed = api_keys_service.parse_keys(raw)
    assert parsed == {
        "alice": ("s1", False, False),
        "aud": ("k", False, True),
    }


def test_parse_keys_rejects_unknown_third_token() -> None:
    with pytest.raises(ValueError, match="unknown scope"):
        api_keys_service.parse_keys("alice:s1:unknownscope")


def test_parse_keys_rejects_missing_colon() -> None:
    with pytest.raises(ValueError, match="name:secret"):
        api_keys_service.parse_keys("nope-no-colon")


def test_parse_keys_rejects_empty_components() -> None:
    with pytest.raises(ValueError, match="empty"):
        api_keys_service.parse_keys(":lonely-secret")
    with pytest.raises(ValueError, match="empty"):
        api_keys_service.parse_keys("name-only:")


def test_parse_keys_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        api_keys_service.parse_keys("hermes:a\nhermes:b")


# ---------------------------------------------------------------------------
# bootstrap_from_env / create_api_key / revoke / verify_bearer (DB-backed)
# ---------------------------------------------------------------------------


def _wipe_api_keys() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


def test_bootstrap_from_env_inserts_idempotently() -> None:
    _wipe_api_keys()
    inserted = api_keys_service.bootstrap_from_env(
        app.state.session_factory,
        env={"POINTLESSQL_API_KEYS": "alice:s1, sup:godkey:supervisor"},
    )
    assert inserted == 2

    # Second run is a no-op even though env unchanged.
    again = api_keys_service.bootstrap_from_env(
        app.state.session_factory,
        env={"POINTLESSQL_API_KEYS": "alice:s1, sup:godkey:supervisor"},
    )
    assert again == 0
    _wipe_api_keys()


def test_create_and_verify_roundtrip() -> None:
    _wipe_api_keys()
    row, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="hermes", supervisor=False
    )
    assert row.name == "hermes"
    assert row.secret_prefix == plaintext[:8]

    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None
    assert entry.name == "hermes"
    assert entry.supervisor is False
    _wipe_api_keys()


def test_revoke_blocks_subsequent_verifies() -> None:
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(app.state.session_factory, name="rotateme")
    assert (
        api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory) is not None
    )
    assert api_keys_service.revoke_api_key(app.state.session_factory, name="rotateme")
    # Cache invalidation makes the revoke take effect immediately.
    assert api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory) is None
    _wipe_api_keys()


def test_supervisor_scope_propagates_to_entry() -> None:
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="sup", supervisor=True
    )
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None and entry.supervisor is True
    _wipe_api_keys()


def test_verify_bearer_short_circuits_without_factory() -> None:
    assert api_keys_service.verify_bearer("Bearer abc", None) is None


def test_verify_bearer_ignores_non_bearer_schemes() -> None:
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(app.state.session_factory, name="hermes")
    factory = app.state.session_factory
    assert api_keys_service.verify_bearer(f"Basic {plaintext}", factory) is None
    assert api_keys_service.verify_bearer(plaintext, factory) is None
    assert api_keys_service.verify_bearer(None, factory) is None
    assert api_keys_service.verify_bearer("Bearer ", factory) is None
    _wipe_api_keys()


# ---------------------------------------------------------------------------
# HTTP-level integration via ASGI transport
# ---------------------------------------------------------------------------


@pytest.fixture
def gate_secret() -> Iterator[str]:
    """Provision a single Bearer-eligible key and yield its plaintext."""
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(app.state.session_factory, name="hermes")
    try:
        yield plaintext
    finally:
        _wipe_api_keys()


@pytest.mark.asyncio
async def test_api_route_rejects_unauthenticated_without_bearer(
    gate_secret: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/api/agent-runs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_route_rejects_wrong_bearer_secret(
    gate_secret: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs",
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_route_accepts_valid_bearer(gate_secret: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {gate_secret}"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)


@pytest.mark.asyncio
async def test_bearer_creates_audit_row_with_api_key_name(
    gate_secret: str,
) -> None:
    """A POST authenticated by Bearer must still leave an audit trail."""
    source = "print('hello')\n"
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {gate_secret}"},
            json={
                "id": run_id,
                "notebook_path": "demo/run.py",
                "source": source,
                "runtime_versions": {"python": "3.14.0"},
            },
        )
    assert response.status_code == 200, response.text
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(select(AuditLog).where(AuditLog.target == f"agent_run:{run_id}"))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_role == "system"
    assert row.user_email == "api_key:hermes"
    assert row.user_id == 0
    assert row.detail and "hermes" in row.detail


@pytest.mark.asyncio
async def test_x_principal_overrides_api_key_email_in_audit(
    gate_secret: str,
) -> None:
    """``X-Principal`` re-attributes the row to a human."""
    source = "print('hello')\n"
    run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.post(
            "/api/agent-runs",
            headers={
                "Authorization": f"Bearer {gate_secret}",
                "X-Principal": "alice@example.com",
            },
            json={
                "id": run_id,
                "notebook_path": "demo/run.py",
                "source": source,
                "runtime_versions": {"python": "3.14.0"},
            },
        )
    assert response.status_code == 200, response.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(AuditLog).where(AuditLog.target == f"agent_run:{run_id}")
        ).scalar_one()
    assert row.user_email == "alice@example.com"
    assert row.detail and "hermes" in row.detail


@pytest.mark.asyncio
async def test_gate_disabled_ignores_bearer_header(auth_cookies) -> None:
    """When the api_keys table is empty, Bearer requests are unauthorised."""
    _wipe_api_keys()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs",
            headers={"Authorization": "Bearer some-random-secret"},
        )
    assert response.status_code == 401
    # Cookie auth still works.
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://t",
        cookies=auth_cookies,
    ) as c:
        response = await c.get("/api/agent-runs")
    assert response.status_code == 200
