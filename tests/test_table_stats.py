"""Tests for column statistics."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.services import table_stats as ts

# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    loc = str(tmp_path / "orders")
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "category": ["a", "b", "a", "c", "a"],
            "amount": [10.0, 20.0, 15.0, None, 30.0],
        }
    )
    deltalake.write_deltalake(loc, df)
    return loc


def _stub_orders_table(stub: MagicMock, storage_location: str) -> None:
    """Configure the shared ``uc_client_stub`` to serve the orders table."""
    stub.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
            "columns": [
                {"name": "id", "type_text": "bigint"},
                {"name": "category", "type_text": "string"},
                {"name": "amount", "type_text": "double"},
            ],
        }
    )
    stub.get_effective_permissions = AsyncMock(return_value=[])


# ---------------------------------------------------------------------------
# Pure service layer


def test_compute_stats_produces_expected_columns(orders_delta: str) -> None:
    stats = ts.compute_stats(
        "main.sales.orders",
        orders_delta,
        columns=[
            {"name": "id", "type": "BIGINT"},
            {"name": "category", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
    )
    assert set(stats.keys()) == {"id", "category", "amount"}

    id_stats = stats["id"]
    assert id_stats["count"] == 5
    assert id_stats["null_count"] == 0
    assert id_stats["distinct_count"] == 5
    assert id_stats["is_numeric"] is True
    assert id_stats["mean"] == pytest.approx(3.0)

    cat_stats = stats["category"]
    assert cat_stats["count"] == 5
    assert cat_stats["distinct_count"] == 3
    assert cat_stats["mean"] is None, "Non-numeric columns never get a mean"
    assert isinstance(cat_stats["top_5"], list)
    # top_5 entries sorted by descending count; "a" appears 3 times.
    assert cat_stats["top_5"][0] == ["a", 3]

    amount_stats = stats["amount"]
    assert amount_stats["null_count"] == 1
    assert amount_stats["is_numeric"] is True


def test_compute_stats_skips_top_5_when_distinct_above_ceiling(
    orders_delta: str,
) -> None:
    stats = ts.compute_stats(
        "main.sales.orders",
        orders_delta,
        columns=[{"name": "id", "type": "BIGINT"}],
        top_k_ceiling=2,  # below the actual distinct count (5)
    )
    assert stats["id"]["top_5"] is None


def test_cache_round_trip_evicts_stale_version() -> None:
    factory = app.state.session_factory
    full_name = "main.sales.orders"
    initial = {"id": {"column_name": "id", "count": 3}}
    ts.write_cached(
        factory,
        full_name=full_name,
        delta_log_version=1,
        stats=initial,
    )
    cached = ts.read_cached(
        factory,
        full_name=full_name,
        delta_log_version=1,
    )
    assert cached is not None
    assert cached[0]["column_name"] == "id"
    # Re-writing at the same version should overwrite (idempotent).
    updated = {"id": {"column_name": "id", "count": 42}}
    ts.write_cached(
        factory,
        full_name=full_name,
        delta_log_version=1,
        stats=updated,
    )
    again = ts.read_cached(
        factory,
        full_name=full_name,
        delta_log_version=1,
    )
    assert again is not None
    assert again[0]["stats"]["count"] == 42


def test_delete_cached_removes_every_version() -> None:
    factory = app.state.session_factory
    ts.write_cached(
        factory,
        full_name="main.sales.orders",
        delta_log_version=1,
        stats={"id": {"count": 1}},
    )
    ts.write_cached(
        factory,
        full_name="main.sales.orders",
        delta_log_version=2,
        stats={"id": {"count": 2}},
    )
    removed = ts.delete_cached(factory, "main.sales.orders")
    assert removed >= 2
    assert ts.read_cached(factory, full_name="main.sales.orders") is None


def test_read_delta_log_version_reads_a_real_table(orders_delta: str) -> None:
    version = ts.read_delta_log_version(orders_delta)
    # Fresh write produces version 0.
    assert version == 0


# ---------------------------------------------------------------------------
# HTTP surface
#
# These consume the shared ``uc_client_stub`` seam from conftest.py —
# one stub behind both ``app.state.uc_client`` and
# ``UnityCatalogClient.for_principal`` — instead of the per-file
# classmethod patch + raw ``app.state`` assignment this file used to
# carry.


@pytest.mark.asyncio
async def test_profile_and_stats_round_trip_for_admin(
    orders_delta: str, admin_client: httpx.AsyncClient, uc_client_stub: MagicMock
) -> None:
    _stub_orders_table(uc_client_stub, orders_delta)
    full_name = "main.sales.orders"
    profile = await admin_client.post(f"/api/tables/{full_name}/profile")
    assert profile.status_code == 200
    body = profile.json()
    assert body["full_name"] == full_name
    assert body["delta_log_version"] == 0
    assert body["cached"] is False
    names = [c["column_name"] for c in body["columns"]]
    assert set(names) == {"id", "category", "amount"}

    # Second call: cache hit with cached=True.
    profile2 = await admin_client.post(f"/api/tables/{full_name}/profile")
    assert profile2.status_code == 200
    assert profile2.json()["cached"] is True

    # GET /stats returns the cached columns.
    stats_resp = await admin_client.get(f"/api/tables/{full_name}/stats")
    assert stats_resp.status_code == 200
    assert len(stats_resp.json()["columns"]) == 3


@pytest.mark.asyncio
async def test_delete_stats_requires_admin(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    _stub_orders_table(uc_client_stub, orders_delta)
    full_name = "main.sales.orders"
    # Admin populates + clears.
    await admin_client.post(f"/api/tables/{full_name}/profile")
    clear = await admin_client.delete(f"/api/tables/{full_name}/stats")
    assert clear.status_code == 204
    # Non-admin DELETE is 403 even when there are no cached rows.
    forbidden = await non_admin_client.delete(f"/api/tables/{full_name}/stats")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_profile_enforces_select(
    orders_delta: str,
    monkeypatch: pytest.MonkeyPatch,
    non_admin_client: httpx.AsyncClient,
    uc_client_stub: MagicMock,
) -> None:
    """A caller without SELECT on the table is refused at enforcement."""
    _stub_orders_table(uc_client_stub, orders_delta)

    async def deny(
        client: Any,
        email: str,
        is_admin: bool,
        resource_type: str,
        full_name: str,
        privilege: str,
    ) -> None:
        from pointlessql.exceptions import AuthorizationError

        raise AuthorizationError(
            email,
            privilege,
            resource_type,
            full_name,
        )

    # Patch check_privilege at its import site — `_helpers.py` imports
    # the function directly into the module namespace, so the binding
    # `enforce_table_profile_access` resolves against lives there.
    from pointlessql.api.governance_routes import _helpers as _gov_helpers

    monkeypatch.setattr(_gov_helpers, "check_privilege", deny)

    res = await non_admin_client.post("/api/tables/main.sales.orders/profile")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_profile_404_when_table_missing(
    admin_client: httpx.AsyncClient, uc_client_stub: MagicMock
) -> None:
    uc_client_stub.get_table = AsyncMock(return_value=None)
    uc_client_stub.get_effective_permissions = AsyncMock(return_value=[])
    res = await admin_client.post("/api/tables/no.such.table/profile")
    assert res.status_code == 404
