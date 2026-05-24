"""Tests for the query_history service and /api/queries route."""

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


def _seed_history_rows(factory: Any, count: int, user_id: int = 1) -> None:
    """Insert ``count`` synthetic query_history rows newest-first."""
    base = datetime.datetime(2026, 4, 1, 12, 0, 0, tzinfo=datetime.UTC)
    for i in range(count):
        qh.record_query(
            factory,
            user_id=user_id,
            user_email=f"user{user_id}@test.com",
            sql_text=f"SELECT {i}",
            started_at=base + datetime.timedelta(seconds=i),
            finished_at=base + datetime.timedelta(seconds=i, milliseconds=10),
            status="succeeded",
            row_count=1,
            duration_ms=10,
            referenced_tables=[],
        )


def test_list_queries_offset_streams_pages() -> None:
    factory = app.state.session_factory
    # Clean slate — caller controls the row count for stable assertions.
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    _seed_history_rows(factory, count=12, user_id=1)

    page1 = qh.list_queries(factory, user_id=1, limit=5, offset=0)
    page2 = qh.list_queries(factory, user_id=1, limit=5, offset=5)
    page3 = qh.list_queries(factory, user_id=1, limit=5, offset=10)

    assert len(page1) == 5
    assert len(page2) == 5
    assert len(page3) == 2
    page1_ids = {r["id"] for r in page1}
    page2_ids = {r["id"] for r in page2}
    page3_ids = {r["id"] for r in page3}
    assert page1_ids.isdisjoint(page2_ids)
    assert page2_ids.isdisjoint(page3_ids)


def test_count_queries_honours_filters() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    _seed_history_rows(factory, count=4, user_id=1)
    _seed_history_rows(factory, count=3, user_id=2)

    assert qh.count_queries(factory) == 7
    assert qh.count_queries(factory, user_id=1) == 4
    assert qh.count_queries(factory, user_id=2) == 3
    assert qh.count_queries(factory, user_id=99) == 0


async def test_queries_page_emits_pager_when_more_pages_remain(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    _seed_history_rows(factory, count=60, user_id=1)

    resp = await admin_client.get("/queries")
    assert resp.status_code == 200
    body = resp.text
    # Default page size is 50, so 60 rows → next_offset=50 must surface.
    assert "Load 50 more" in body
    assert "10 remaining" in body
    assert "Showing 50 of 60" in body


async def test_queries_page_htmx_returns_partial(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    _seed_history_rows(factory, count=80, user_id=1)

    resp = await admin_client.get(
        "/queries?offset=50",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    body = resp.text
    # Partial response — no full <html> shell, only fragment + OOB pager.
    assert "<!doctype html>" not in body.lower()
    assert "queries-pager" in body
    assert 'hx-swap-oob="true"' in body
    # offset=50 + page=50 = 100 ≥ total=80 → no further next_offset link.
    assert "All 80 entries loaded." in body


async def test_queries_page_emits_rows_with_hljs_marker(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    """The /queries page paints a row per history entry with hljs hooks.

    The page went table → card-grid → table (Phase 61/62
    drift roll-up); current shape is a Bootstrap table whose
    ``<tbody>`` carries id ``queries-tbody`` and each drawer body
    contains a ``<code class="language-sql">`` hook for highlight.js.
    Seed a SQL long enough to surface the drawer so the
    ``language-sql`` marker actually renders.
    """
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    long_sql = "SELECT " + ", ".join([f"c_{i}" for i in range(120)]) + " FROM main.t"
    qh.record_query(
        factory,
        user_id=1,
        user_email="x@y.z",
        sql_text=long_sql,
        started_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
        finished_at=datetime.datetime(2026, 4, 1, 0, 0, 0, 100000, tzinfo=datetime.UTC),
        status="succeeded",
        row_count=1,
        duration_ms=100,
        referenced_tables=[],
    )
    resp = await admin_client.get("/queries")
    assert resp.status_code == 200
    body = resp.text
    # Table layout markers + status badge + hljs hook in drawer body.
    assert 'id="queries-tbody"' in body
    assert 'class="badge bg-success">succeeded' in body
    assert 'class="language-sql"' in body
    # hljs CDN + page-local highlight bridge are loaded only on /queries.
    assert "highlight.min.js" in body
    assert "/static/js/sql_highlight.js" in body


async def test_queries_card_emits_drawer_trigger_for_long_sql(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    """SQL longer than 700 chars surfaces a drawer-trigger button."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    long_sql = "SELECT " + ", ".join([f"col_{i}" for i in range(120)]) + " FROM main.t"
    assert len(long_sql) > 700
    qh.record_query(
        factory,
        user_id=1,
        user_email="x@y.z",
        sql_text=long_sql,
        started_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
        finished_at=datetime.datetime(2026, 4, 1, 0, 0, 0, 100000, tzinfo=datetime.UTC),
        status="succeeded",
        row_count=1,
        duration_ms=100,
        referenced_tables=[],
    )
    resp = await admin_client.get("/queries")
    assert resp.status_code == 200
    body = resp.text
    assert "View full SQL" in body
    assert 'data-bs-toggle="offcanvas"' in body
    assert "drawer-q-" in body  # macro id prefix


async def test_queries_card_omits_drawer_for_short_sql(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    """Short SQL renders without the drawer trigger — no UI clutter."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    qh.record_query(
        factory,
        user_id=1,
        user_email="x@y.z",
        sql_text="SELECT 1",
        started_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
        finished_at=datetime.datetime(2026, 4, 1, 0, 0, 0, 100000, tzinfo=datetime.UTC),
        status="succeeded",
        row_count=1,
        duration_ms=100,
        referenced_tables=[],
    )
    resp = await admin_client.get("/queries")
    assert resp.status_code == 200
    assert "View full SQL" not in resp.text


async def test_queries_page_status_filter_narrows_results(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    base = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    for i, st in enumerate(["succeeded", "succeeded", "failed", "cancelled"]):
        qh.record_query(
            factory,
            user_id=1,
            user_email="x@y.z",
            sql_text=f"SELECT {i}",
            started_at=base + datetime.timedelta(seconds=i),
            finished_at=base + datetime.timedelta(seconds=i, milliseconds=10),
            status=st,
            row_count=1,
            duration_ms=10,
            referenced_tables=[],
        )

    resp = await admin_client.get("/queries?status=failed")
    assert resp.status_code == 200
    assert "Showing 1 of 1 entry" in resp.text


async def test_queries_page_htmx_passes_filter_params_through(
    orders_delta: str,
    admin_client: httpx.AsyncClient,
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    factory = app.state.session_factory
    with factory() as session:
        session.query(QueryHistoryTable).delete()
        session.query(QueryHistory).delete()
        session.commit()
    _seed_history_rows(factory, count=70, user_id=1)

    resp = await admin_client.get(
        "/queries?read_kind=sql_execute",
    )
    assert resp.status_code == 200
    # Pager URL must propagate read_kind so subsequent pages honour the filter.
    assert "read_kind=sql_execute" in resp.text
