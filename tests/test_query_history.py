"""Tests for the Phase-12 query_history service and /api/queries route."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import QueryHistory, QueryHistoryTable
from pointlessql.services import query_history as qh
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_uc_mock(
    *,
    storage_location: str,
    effective: list[dict[str, Any]] | None = None,
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
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
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
    df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    deltalake.write_deltalake(loc, df)
    return loc


# -- service-level -------------------------------------------------


def test_record_query_persists_row_and_joined_tables() -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    qh_id = qh.record_query(
        factory,
        user_id=1,
        user_email="x@y.z",
        sql_text="SELECT * FROM main.sales.orders",
        started_at=now,
        finished_at=now + datetime.timedelta(milliseconds=12),
        status="succeeded",
        row_count=3,
        duration_ms=12,
        referenced_tables=["main.sales.orders"],
    )
    assert qh_id > 0

    with factory() as session:
        row = session.scalar(select(QueryHistory).where(QueryHistory.id == qh_id))
        assert row is not None
        assert row.status == "succeeded"
        assert row.row_count == 3
        tables = list(
            session.scalars(
                select(QueryHistoryTable).where(QueryHistoryTable.query_history_id == qh_id)
            )
        )
        assert [t.full_name for t in tables] == ["main.sales.orders"]
        assert tables[0].access_type == "read"


def test_record_query_failure_keeps_error_message() -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    qh.record_query(
        factory,
        user_id=2,
        user_email="oops@test.com",
        sql_text="SELECT bogus",
        started_at=now,
        finished_at=now,
        status="failed",
        row_count=None,
        duration_ms=None,
        referenced_tables=[],
        error_message="Binder Error: column 'bogus' does not exist",
    )
    rows = qh.list_queries(factory, status="failed")
    assert any("column 'bogus'" in (r["error_message"] or "") for r in rows)


def test_list_queries_filters_by_user_and_status() -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    # User 1: succeeded, user 2: failed.
    qh.record_query(
        factory,
        user_id=1,
        user_email="a@test.com",
        sql_text="SELECT 1",
        started_at=now,
        finished_at=now,
        status="succeeded",
        row_count=1,
        duration_ms=5,
        referenced_tables=[],
    )
    qh.record_query(
        factory,
        user_id=2,
        user_email="b@test.com",
        sql_text="SELECT bogus",
        started_at=now,
        finished_at=now,
        status="failed",
        row_count=None,
        duration_ms=None,
        referenced_tables=[],
        error_message="boom",
    )
    u1 = qh.list_queries(factory, user_id=1)
    u2 = qh.list_queries(factory, user_id=2)
    assert all(r["user_id"] == 1 for r in u1)
    assert all(r["user_id"] == 2 for r in u2)
    failed = qh.list_queries(factory, status="failed")
    assert all(r["status"] == "failed" for r in failed)


def test_list_queries_reverse_lookup_by_table() -> None:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    qh.record_query(
        factory,
        user_id=1,
        user_email="a@test.com",
        sql_text="SELECT * FROM main.sales.orders",
        started_at=now,
        finished_at=now,
        status="succeeded",
        row_count=3,
        duration_ms=5,
        referenced_tables=["main.sales.orders"],
    )
    qh.record_query(
        factory,
        user_id=1,
        user_email="a@test.com",
        sql_text="SELECT * FROM main.sales.customers",
        started_at=now,
        finished_at=now,
        status="succeeded",
        row_count=5,
        duration_ms=7,
        referenced_tables=["main.sales.customers"],
    )
    all_rows = qh.list_queries(factory, user_id=1)
    tables_per_row = [set(r["tables"]) for r in all_rows]
    assert {"main.sales.orders"} in tables_per_row
    assert {"main.sales.customers"} in tables_per_row


# -- route-level ---------------------------------------------------


async def test_execute_success_writes_history_row(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT * FROM main.sales.orders ORDER BY id"},
    )
    assert resp.status_code == 200, resp.text

    factory = app.state.session_factory
    with factory() as session:
        rows = list(session.scalars(select(QueryHistory).order_by(QueryHistory.id.desc())))
        assert rows, "expected at least one query_history row"
        # The new row should be first (DESC order).
        latest = rows[0]
        assert latest.status == "succeeded"
        assert latest.row_count == 3
        tables = list(
            session.scalars(
                select(QueryHistoryTable).where(QueryHistoryTable.query_history_id == latest.id)
            )
        )
        assert [t.full_name for t in tables] == ["main.sales.orders"]


async def test_execute_parse_failure_writes_failed_history(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELEC * FROM x"},
    )
    assert resp.status_code == 400

    factory = app.state.session_factory
    rows = qh.list_queries(factory, status="failed")
    assert any("Could not parse" in (r["error_message"] or "") for r in rows)


async def test_api_queries_non_admin_sees_only_own_rows(
    orders_delta: str, non_admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(
        storage_location=orders_delta,
        effective=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}],
    )
    # Non-admin runs a query.
    resp = await non_admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT * FROM main.sales.orders"},
    )
    assert resp.status_code == 200, resp.text

    # Non-admin lists own queries — should see their row, nothing else.
    resp = await non_admin_client.get("/api/queries")
    assert resp.status_code == 200
    body = resp.json()
    assert body
    for row in body:
        assert row["user_email"] == "nonadmin@test.com"


async def test_queries_page_renders(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    # Seed one row so the page exercises the populated branch.
    await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT * FROM main.sales.orders"},
    )
    resp = await admin_client.get("/queries")
    assert resp.status_code == 200
    assert b"Query history" in resp.content
