"""Visual Query Builder unit + route smoke tests.

The unit half exercises ``build_sql_from_state`` /
``parse_sql_to_state`` for the round-trip and the supported-subset
edges.  The route half verifies the /api/sql/builder/* endpoints
respond with the expected envelope (column probe is gated on a
soyuz roundtrip we don't seed here so it's skipped).
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.services.sql.builder import (
    build_sql_from_state,
    parse_sql_to_state,
)


def test_build_select_with_filters_group_aggregates_order_limit() -> None:
    """Full state renders to a single SELECT with every clause."""
    sql = build_sql_from_state(
        {
            "table_fqn": "main.sales.orders",
            "filters": [
                {"column": "country", "op": "=", "value": "DE"},
                {"column": "amount", "op": ">", "value": 100},
            ],
            "group_by": ["country"],
            "aggregates": [
                {"fn": "COUNT", "column": "*", "alias": "n"},
                {"fn": "SUM", "column": "amount", "alias": "total"},
            ],
            "order_by": [{"column": "total", "dir": "desc"}],
            "limit": 50,
        }
    )
    assert "SELECT" in sql
    assert "FROM main.sales.orders" in sql
    assert "WHERE" in sql
    assert "GROUP BY" in sql
    assert "ORDER BY" in sql
    assert "LIMIT 50" in sql


def test_build_requires_table_fqn() -> None:
    """Empty table_fqn raises."""
    with pytest.raises(ValueError):
        build_sql_from_state({"table_fqn": ""})


def test_build_requires_three_part_table() -> None:
    """Non-three-part table_fqn raises."""
    with pytest.raises(ValueError):
        build_sql_from_state({"table_fqn": "orders"})


def test_round_trip_simple() -> None:
    """Build → parse → equal-ish state for a supported shape."""
    state = {
        "table_fqn": "main.sales.orders",
        "filters": [{"column": "country", "op": "=", "value": "DE"}],
        "group_by": ["country"],
        "aggregates": [{"fn": "COUNT", "column": "*", "alias": "n"}],
        "order_by": [],
        "limit": None,
    }
    sql = build_sql_from_state(state)
    parsed = parse_sql_to_state(sql)
    assert parsed is not None
    assert parsed["table_fqn"] == "main.sales.orders"
    assert parsed["group_by"] == ["country"]
    assert parsed["aggregates"] == [{"fn": "COUNT", "column": "*", "alias": "n"}]
    assert parsed["filters"][0]["column"] == "country"
    assert parsed["filters"][0]["op"] == "="
    assert parsed["filters"][0]["value"] == "DE"


def test_round_trip_is_null() -> None:
    """IS NULL filters survive the round-trip."""
    sql = build_sql_from_state(
        {
            "table_fqn": "main.sales.orders",
            "filters": [{"column": "deleted_at", "op": "IS NULL", "value": None}],
        }
    )
    parsed = parse_sql_to_state(sql)
    assert parsed is not None
    assert parsed["filters"][0]["op"] == "IS NULL"


def test_parse_returns_none_for_join() -> None:
    """Multi-table SQL is rejected (builder doesn't support JOIN)."""
    assert parse_sql_to_state(
        "SELECT * FROM a.b.c JOIN d.e.f ON c.id = f.id"
    ) is None


def test_parse_returns_none_for_subquery() -> None:
    """Subqueries are rejected."""
    assert parse_sql_to_state(
        "SELECT * FROM (SELECT 1) t"
    ) is None


def test_parse_returns_none_for_unsupported_select_item() -> None:
    """A computed expression outside an aggregate is rejected."""
    assert parse_sql_to_state(
        "SELECT col1 + col2 FROM a.b.c"
    ) is None


@pytest.mark.asyncio
async def test_operators_endpoint(admin_client: httpx.AsyncClient) -> None:
    """The /operators endpoint exposes the supported sets."""
    res = await admin_client.get("/api/sql/builder/operators")
    assert res.status_code == 200
    body = res.json()
    assert "=" in body["operators"]
    assert "SUM" in body["aggregates"]


@pytest.mark.asyncio
async def test_build_endpoint(admin_client: httpx.AsyncClient) -> None:
    """The /build endpoint returns a SELECT for valid state."""
    res = await admin_client.post(
        "/api/sql/builder/build",
        json={
            "table_fqn": "main.sales.orders",
            "filters": [{"column": "x", "op": "=", "value": 1}],
            "limit": 10,
        },
    )
    assert res.status_code == 200, res.text
    assert "SELECT" in res.json()["sql"]


@pytest.mark.asyncio
async def test_parse_endpoint_round_trip(admin_client: httpx.AsyncClient) -> None:
    """The /parse endpoint mirrors the unit-level round-trip."""
    res = await admin_client.post(
        "/api/sql/builder/parse",
        json={"sql": "SELECT * FROM main.sales.orders LIMIT 10"},
    )
    assert res.status_code == 200
    state = res.json()["state"]
    assert state is not None
    assert state["table_fqn"] == "main.sales.orders"
    assert state["limit"] == 10


@pytest.mark.asyncio
async def test_parse_endpoint_returns_null_for_join(
    admin_client: httpx.AsyncClient,
) -> None:
    """JOIN SQL returns ``state=None`` so the UI falls back."""
    res = await admin_client.post(
        "/api/sql/builder/parse",
        json={"sql": "SELECT 1 FROM a.b.c JOIN d.e.f ON 1=1"},
    )
    assert res.status_code == 200
    assert res.json()["state"] is None
