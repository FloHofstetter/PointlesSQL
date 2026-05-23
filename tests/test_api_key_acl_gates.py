"""Tests for the Phase 120.3 wiring of ACL checks into routes.

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


def _add_catalog_grant(
    *, api_key_id: int, catalog_name: str, schema_name: str | None
) -> None:
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
    _add_catalog_grant(
        api_key_id=sql_execute_secret.row.id, catalog_name="main", schema_name=None
    )
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
    assert body["error_code"] == "IP_NOT_ALLOWED"
