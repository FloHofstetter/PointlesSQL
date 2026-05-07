"""Route-level tests for POST /api/sql/execute."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_uc_mock(
    *,
    storage_location: str,
    effective: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a UnityCatalogClient mock that resolves one table.

    Args:
        storage_location: Path to return as ``storage_location`` for
            every ``get_table`` call.
        effective: Effective-permissions payload to return.  Defaults
            to an empty list (no grants).

    Returns:
        A mock suitable for patching onto ``app.state.uc_client``.
    """
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``UnityCatalogClient.for_principal`` to ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    """Create a tiny Delta table at ``tmp_path/orders`` and return its path."""
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "name": ["a", "b", "c", "d", "e"]})
    deltalake.write_deltalake(loc, df)
    return loc




async def test_admin_executes_query_and_sees_rows(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id, name FROM main.sales.orders ORDER BY id"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["referenced_tables"] == ["main.sales.orders"]
    assert body["row_count"] == 5
    assert body["truncated"] is False
    assert body["columns"][0]["name"] == "id"
    assert body["rows"][0] == [1, "a"]


async def test_non_admin_without_select_is_denied(orders_delta: str, non_admin_client: httpx.AsyncClient) -> None:
    # empty effective perms → check_privilege should raise 403.
    app.state.uc_client = _make_uc_mock(
        storage_location=orders_delta,
        effective=[],
    )
    resp = await non_admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT * FROM main.sales.orders"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "authorization_error"
    assert body["full_name"] == "main.sales.orders"
    assert body["required_privilege"] == "SELECT"


async def test_non_admin_with_select_grant_succeeds(orders_delta: str, non_admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(
        storage_location=orders_delta,
        effective=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}],
    )
    resp = await non_admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT COUNT(*) AS n FROM main.sales.orders"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == [[5]]


async def test_malformed_sql_returns_400_problem_json(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELEC * FROM x"},
    )
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["code"] == "sql_execution_error"


async def test_two_part_reference_is_rejected(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT * FROM sales.orders"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "sql_execution_error"
    assert "catalog.schema.table" in body["detail"]


async def test_row_cap_is_applied(orders_delta: str, monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient) -> None:
    # Clamp max_rows to 3 so our 5-row Delta table gets truncated.
    monkeypatch.setattr(app.state.settings.sql, "max_rows", 3)
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id, name FROM main.sales.orders ORDER BY id"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count"] == 3
    assert body["truncated"] is True


async def test_select_with_no_tables_succeeds(admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location="/nonexistent")
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT 1 AS n"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == [[1]]
    assert body["referenced_tables"] == []


async def test_sql_editor_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/sql")
    assert resp.status_code == 200
    assert b'id="pql-sql-editor-root"' in resp.content
    # The SQL tab should be marked active.
    assert b"active_page" not in resp.content  # server context var, not rendered


async def test_explain_mode_returns_plan_and_skips_history(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    # Capture history row count before the EXPLAIN call so we can
    # assert it did NOT grow (Sprint-53 decision: EXPLAIN is
    # diagnostic, not recorded).
    before = (await admin_client.get("/api/queries")).json()
    before_count = len(before)

    resp = await admin_client.post(
        "/api/sql/execute",
        json={
            "sql": "SELECT id FROM main.sales.orders",
            "explain": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_explain"] is True
    assert isinstance(body["explain_text"], str)
    # Plans are non-empty for a real query.
    assert body["explain_text"]

    after = (await admin_client.get("/api/queries")).json()
    assert len(after) == before_count, "EXPLAIN must not write to query_history"
