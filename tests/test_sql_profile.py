"""Runtime query profiles: engine capture, summariser, execute route."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import QueryHistory
from pointlessql.pql import PQL
from pointlessql.services.sql.profile import summarize_profile
from pointlessql.services.unitycatalog import UnityCatalogClient

# ---------------------------------------------------------------------------
# summarize_profile
# ---------------------------------------------------------------------------


def test_summarize_modern_tree_orders_by_time() -> None:
    """Operators flatten slowest-first with pct shares of measured time."""
    tree = {
        "latency": 0.5,
        "rows_returned": 7,
        "children": [
            {
                "operator_type": "PROJECTION",
                "operator_timing": 0.1,
                "operator_cardinality": 7,
                "children": [
                    {
                        "operator_type": "TABLE_SCAN",
                        "operator_timing": 0.3,
                        "operator_cardinality": 100,
                        "extra_info": {"Table": "orders"},
                    }
                ],
            }
        ],
    }
    summary = summarize_profile(tree)
    assert summary["total_time_ms"] == 500.0
    assert summary["rows_returned"] == 7
    ops = summary["operators"]
    assert ops[0]["operator"] == "TABLE_SCAN"
    assert ops[0]["time_ms"] == 300.0
    assert ops[0]["pct"] == 75.0
    assert ops[0]["rows"] == 100
    assert "Table=orders" in (ops[0]["extra"] or "")
    assert ops[1]["operator"] == "PROJECTION"
    assert ops[1]["pct"] == 25.0


def test_summarize_tolerates_legacy_key_names() -> None:
    """Older profile trees with ``name``/``timing`` keys still summarise."""
    tree = {
        "name": "QUERY",
        "timing": 0.02,
        "children": [{"name": "SEQ_SCAN", "timing": 0.01, "cardinality": 3}],
    }
    summary = summarize_profile(tree)
    names = [op["operator"] for op in summary["operators"]]
    assert "SEQ_SCAN" in names
    assert summary["operator_count"] == 2


def test_summarize_garbage_input_is_empty_not_raising() -> None:
    """Non-dict input yields an empty summary instead of an exception."""
    for garbage in (None, [], "nope", 42):
        summary = summarize_profile(garbage)
        assert summary["operators"] == []
        assert summary["total_time_ms"] == 0


# ---------------------------------------------------------------------------
# engine capture
# ---------------------------------------------------------------------------


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    """Create a tiny Delta table at ``tmp_path/orders`` and return its path."""
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
    deltalake.write_deltalake(loc, df)
    return loc


def test_run_sql_profile_returns_rows_and_tree(orders_delta: str) -> None:
    """``profile=True`` returns the regular rows plus a parseable tree."""
    result = PQL.sql(
        "SELECT id, amount FROM main.sales.orders ORDER BY id",
        approved_tables={"main.sales.orders": orders_delta},
        profile=True,
    )
    assert result.row_count == 3
    assert result.rows[0] == [1, 10.0]
    assert result.profile is not None
    summary = summarize_profile(result.profile)
    assert summary["operator_count"] > 0


def test_run_sql_without_profile_has_none(orders_delta: str) -> None:
    """The default path carries no profile payload."""
    result = PQL.sql(
        "SELECT COUNT(*) AS n FROM main.sales.orders",
        approved_tables={"main.sales.orders": orders_delta},
    )
    assert result.profile is None


# ---------------------------------------------------------------------------
# execute route
# ---------------------------------------------------------------------------


def _make_uc_mock(storage_location: str) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
            "owner": "someone-else@test.com",
            "properties": {},
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=[])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``UnityCatalogClient.for_principal`` to ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


async def test_execute_with_profile_flag(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id FROM main.sales.orders ORDER BY id", "profile": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "select"
    assert body["row_count"] == 3
    assert body["profile"] is not None
    assert body["profile"]["summary"]["operator_count"] > 0
    assert isinstance(body["profile"]["tree"], dict)

    # the history row persists the raw tree for later replay.
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(QueryHistory).order_by(QueryHistory.id.desc()).limit(1)
        ).scalar_one()
        assert row.profile_json is not None
        assert row.status == "succeeded"


async def test_profile_rejected_for_non_select(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "DROP TABLE main.sales.orders", "profile": True},
    )
    assert resp.status_code == 400
    assert "profiling" in resp.json()["detail"].lower()


async def test_explain_wins_over_profile(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    """When both flags are set the EXPLAIN path answers (no rows)."""
    app.state.uc_client = _make_uc_mock(orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={
            "sql": "SELECT id FROM main.sales.orders",
            "profile": True,
            "explain": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_explain"] is True


async def test_plain_select_has_no_profile_key_payload(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id FROM main.sales.orders"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "profile" not in body or body.get("profile") is None
