"""Tests for the Sprint 13.7.0.5 Bearer-token API-key gate.

Front-loaded auth path that lets the upcoming
``hermes-plugin-pointlessql`` (Sprint 13.7.1+) reach
``/api/agent-runs`` and ``/api/sql/*`` without holding a session
cookie. Gate is configured via ``POINTLESSQL_API_KEYS`` and
short-circuits to "disabled" when unset so the existing
single-user dev flow (``agent_drift_monitor`` walkthrough) keeps
working unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AuditLog
from pointlessql.services import api_keys as api_keys_service

# ---------------------------------------------------------------------------
# parse_keys / verify_bearer (pure functions, no HTTP)
# ---------------------------------------------------------------------------


def test_parse_keys_empty_returns_empty_mapping() -> None:
    assert api_keys_service.parse_keys(None) == {}
    assert api_keys_service.parse_keys("") == {}
    assert api_keys_service.parse_keys("   \n\n  ") == {}


def test_parse_keys_supports_newline_and_comma() -> None:
    raw = "hermes:abc123\npaperclip:xyz789, bot:secret"
    parsed = api_keys_service.parse_keys(raw)
    assert parsed == {
        "hermes": "abc123",
        "paperclip": "xyz789",
        "bot": "secret",
    }


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


def test_verify_bearer_short_circuits_when_disabled() -> None:
    assert api_keys_service.verify_bearer("Bearer abc", {}) is None


def test_verify_bearer_matches_known_secret() -> None:
    keys = {"hermes": "abc123", "paperclip": "xyz789"}
    assert api_keys_service.verify_bearer("Bearer abc123", keys) == "hermes"
    assert api_keys_service.verify_bearer("Bearer xyz789", keys) == "paperclip"


def test_verify_bearer_rejects_wrong_secret() -> None:
    assert (
        api_keys_service.verify_bearer("Bearer wrong", {"hermes": "abc123"})
        is None
    )


def test_verify_bearer_ignores_non_bearer_schemes() -> None:
    keys = {"hermes": "abc123"}
    assert api_keys_service.verify_bearer("Basic abc123", keys) is None
    assert api_keys_service.verify_bearer("abc123", keys) is None
    assert api_keys_service.verify_bearer(None, keys) is None
    assert api_keys_service.verify_bearer("Bearer ", keys) is None


def test_verify_bearer_is_case_insensitive_on_scheme() -> None:
    keys = {"hermes": "abc123"}
    assert api_keys_service.verify_bearer("bearer abc123", keys) == "hermes"
    assert api_keys_service.verify_bearer("BEARER abc123", keys) == "hermes"


# ---------------------------------------------------------------------------
# HTTP-level integration via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def gate_enabled() -> Iterator[None]:
    """Configure ``app.state.api_keys`` for the test then restore."""
    previous = getattr(app.state, "api_keys", {})
    app.state.api_keys = {"hermes": "abc123"}
    try:
        yield
    finally:
        app.state.api_keys = previous


@pytest.mark.asyncio
async def test_api_route_rejects_unauthenticated_without_bearer(
    gate_enabled: None,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/api/agent-runs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_route_rejects_wrong_bearer_secret(
    gate_enabled: None,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs",
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_route_accepts_valid_bearer(gate_enabled: None) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs",
            headers={"Authorization": "Bearer abc123"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload or "agent_runs" in payload or isinstance(payload, dict)


@pytest.mark.asyncio
async def test_bearer_creates_audit_row_with_api_key_name(
    gate_enabled: None,
) -> None:
    """A POST authenticated by Bearer must still leave an audit trail.

    Pre-Sprint-13.7.0.5 the ``audit`` helper bailed out when
    ``user_id == 0`` — Bearer-only requests carry exactly that, so
    the helper now writes a ``actor_role="system"`` row keyed
    ``api_key:<name>`` whenever ``request.state.api_key_name`` is
    set.
    """
    source = "print('hello')\n"
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.post(
            "/api/agent-runs",
            headers={"Authorization": "Bearer abc123"},
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
            session.execute(
                select(AuditLog).where(AuditLog.target == f"agent_run:{run_id}")
            )
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
    gate_enabled: None,
) -> None:
    """``X-Principal`` re-attributes the row to a human."""
    source = "print('hello')\n"
    run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.post(
            "/api/agent-runs",
            headers={
                "Authorization": "Bearer abc123",
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
    # The api_key marker still shows in detail so traceability is
    # preserved even when human attribution wins for the email.
    assert row.detail and "hermes" in row.detail


@pytest.mark.asyncio
async def test_gate_disabled_ignores_bearer_header(auth_cookies) -> None:
    """When ``app.state.api_keys`` is empty, Bearer requests get 401."""
    previous = getattr(app.state, "api_keys", {})
    app.state.api_keys = {}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t"
        ) as c:
            response = await c.get(
                "/api/agent-runs",
                headers={"Authorization": "Bearer abc123"},
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
    finally:
        app.state.api_keys = previous


@pytest.mark.asyncio
async def test_cookie_wins_over_bearer_when_both_present(
    gate_enabled: None,
    auth_cookies,
) -> None:
    """A logged-in human keeps their identity even with a Bearer header."""
    source = "print('hello')\n"
    run_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://t",
        cookies=auth_cookies,
    ) as c:
        response = await c.post(
            "/api/agent-runs",
            headers={"Authorization": "Bearer abc123"},
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
    # Cookie user (test@test.com) attributed; api_key NOT in detail
    # because middleware short-circuited on the cookie path.
    assert row.user_email == "test@test.com"
    assert row.actor_role == "admin"
