"""Tests for the wiring of ACL checks into routes.

Catalog gate is verified end-to-end via the public
``/api/2.0/sql/statements`` route since that's the only surface
that integrates the gate today.  IP gate is verified end-to-end
via the same surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.models import ApiKeyCatalogGrant, ApiKeyIpGrant
from pointlessql.services.unitycatalog import UnityCatalogClient
from tests.conftest import ApiKeyFixture


def _make_uc_mock(
    *, storage_location: str, principal: str = "api_key:sql-execute-fixture"
) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(
        return_value=[{"principal": principal, "privileges": ["SELECT"]}]
    )
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    loc = str(tmp_path / "orders")
    deltalake.write_deltalake(loc, pd.DataFrame({"order_id": [1, 2, 3]}))
    return loc


def _make_client(headers: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
    )


def _add_catalog_grant(*, api_key_id: int, catalog_name: str, schema_name: str | None) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            ApiKeyCatalogGrant(
                api_key_id=api_key_id,
                catalog_name=catalog_name,
                schema_name=schema_name,
                granted_at=datetime.now(UTC),
            )
        )
        session.commit()


def _add_ip_grant(*, api_key_id: int, cidr: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            ApiKeyIpGrant(
                api_key_id=api_key_id,
                cidr=cidr,
                granted_at=datetime.now(UTC),
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Catalog gate via /api/2.0/sql/statements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_catalog_grants_passes_through(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    """Zero grants = unrestricted (back-compat for every pre-120 key)."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT order_id FROM main.sales.orders"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"]["state"] == "SUCCEEDED", body


@pytest.mark.asyncio
async def test_catalog_grant_allows_matching_table(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    _add_catalog_grant(
        api_key_id=sql_execute_secret.row.id, catalog_name="main", schema_name="sales"
    )
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT order_id FROM main.sales.orders"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"]["state"] == "SUCCEEDED", body


@pytest.mark.asyncio
async def test_catalog_grant_blocks_other_schema(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    _add_catalog_grant(
        api_key_id=sql_execute_secret.row.id, catalog_name="main", schema_name="sales"
    )
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT * FROM main.payroll.secret_table"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"]["state"] == "FAILED"
    assert body["status"]["error"]["error_code"] == "PERMISSION_DENIED"
    assert "payroll" in body["status"]["error"]["message"]


@pytest.mark.asyncio
async def test_catalog_wildcard_schema_allows_any_schema(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    _add_catalog_grant(api_key_id=sql_execute_secret.row.id, catalog_name="main", schema_name=None)
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT order_id FROM main.sales.orders"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"]["state"] == "SUCCEEDED"


# ---------------------------------------------------------------------------
# IP gate via middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ip_grant_present_but_source_matches(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    """Granting 127.0.0.0/8 + 0.0.0.0/0 covers test-client + fallback."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    # ASGI test client may report source as "" / "testclient" / "127.0.0.1".
    # 0.0.0.0/0 always matches when an IP is present.
    _add_ip_grant(api_key_id=sql_execute_secret.row.id, cidr="0.0.0.0/0")
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT order_id FROM main.sales.orders"},
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_ip_grant_present_but_source_blocked(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    """A 10.0.0.0/8-only grant blocks a non-internal source."""
    _add_ip_grant(api_key_id=sql_execute_secret.row.id, cidr="10.0.0.0/8")
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1 AS one"},
        )
    assert resp.status_code == 403
    body = resp.json()
    # middleware emits RFC 9457 problem+json now.
    assert body["status"] == 403
    assert body["code"] == "ip_not_allowed"
    assert body["source_ip"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_ip_grant_enforced_even_with_global_flag_off(
    sql_execute_secret: ApiKeyFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key's own ip-grants are enforced even with the global flag off.

    The global ``enforce_ip_grants`` kill-switch must not silently disable
    a key's explicit allowlist — that would turn a misconfigured incident
    switch into a security downgrade.
    """
    monkeypatch.setattr(app.state.settings.api_key_acl, "enforce_ip_grants", False)
    _add_ip_grant(api_key_id=sql_execute_secret.row.id, cidr="10.0.0.0/8")
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1 AS one"},
        )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ip_not_allowed"


@pytest.mark.asyncio
async def test_bearer_ignored_on_non_allowlisted_html_path(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    """A valid Bearer key on an HTML path does not authenticate the request.

    Bearer acceptance is restricted to the integration path prefixes, so a
    leaked key presented against the browser UI is ignored and the request
    falls through to the login redirect.
    """
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.get("/catalog", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_bearer_still_accepted_on_api_path(
    sql_execute_secret: ApiKeyFixture, orders_delta: str
) -> None:
    """The allowlist's positive case: the key still authenticates under /api."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with _make_client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT order_id FROM main.sales.orders"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"]["state"] == "SUCCEEDED"
