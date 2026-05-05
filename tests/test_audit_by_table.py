"""Phase 18.8 — runs-by-table reverse-index.

Verifies the three relationship axes (touched / written / read)
return the expected runs without overlap, and that the HTML page
renders.  Source-row seeding goes directly through the SQLAlchemy
session because the reverse index doesn't change schema; we just
exercise existing tables.
"""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageValueChange,
    QueryHistory,
    QueryHistoryTable,
)


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_run(*, run_id: str, tables: list[str] | None = None) -> None:
    """Insert one :class:`AgentRun` row with the given declared tables."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal=f"{run_id[:4]}@example.com",
                agent_id="rev-index",
                notebook_path="rev/job.py",
                source_snapshot_sha="0" * 64,
                status="succeeded",
                started_at=dt.datetime.now(dt.UTC),
                tables_touched=json.dumps(tables) if tables is not None else None,
            )
        )
        session.commit()


def _seed_op(*, run_id: str, target: str) -> int:
    factory = app.state.session_factory
    with factory() as session:
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table=target,
            input_sha=None,
            rows_affected=1,
            delta_version_before=0,
            delta_version_after=1,
            started_at=dt.datetime.now(dt.UTC),
            finished_at=dt.datetime.now(dt.UTC),
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return int(op.id)


def _seed_value_change(*, run_id: str, op_id: int, target: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table=target,
                target_row_id="r1",
                target_column="amount",
                old_value="1",
                new_value="2",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _seed_query_with_table(*, run_id: str, full_name: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        qh = QueryHistory(
            user_id=1,
            user_email="reader@example.com",
            sql_text=f"SELECT * FROM {full_name}",
            started_at=dt.datetime.now(dt.UTC),
            finished_at=dt.datetime.now(dt.UTC),
            duration_ms=1,
            status="succeeded",
            read_kind="sql_editor",
            agent_run_id=run_id,
        )
        session.add(qh)
        session.flush()
        session.add(
            QueryHistoryTable(
                query_history_id=qh.id,
                full_name=full_name,
                access_type="read",
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_kind_touched_finds_declared_table() -> None:
    """A run with the FQN in tables_touched surfaces under kind=touched."""
    _seed_run(
        run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        tables=["main.silver.orders", "main.bronze.orders_raw"],
    )
    _seed_run(
        run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        tables=["main.silver.unrelated"],
    )
    async with _admin_client() as c:
        r = await c.get(
            "/api/audit/by-table?fqn=main.silver.orders&kind=touched"
        )
    assert r.status_code == 200, r.text
    payload = r.json()
    ids = {run["id"] for run in payload["runs"]}
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in ids
    assert "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" not in ids


@pytest.mark.asyncio
async def test_kind_written_via_op_target_table() -> None:
    """A run with a merge op against the FQN surfaces under kind=written."""
    _seed_run(run_id="cccccccc-cccc-cccc-cccc-cccccccccccc", tables=[])
    _seed_op(
        run_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        target="main.silver.orders",
    )
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=main.silver.orders&kind=written")
    assert r.status_code == 200, r.text
    ids = {run["id"] for run in r.json()["runs"]}
    assert "cccccccc-cccc-cccc-cccc-cccccccccccc" in ids


@pytest.mark.asyncio
async def test_kind_written_via_value_change() -> None:
    """A run with a value-change against the FQN surfaces under kind=written."""
    _seed_run(run_id="dddddddd-dddd-dddd-dddd-dddddddddddd", tables=[])
    op_id = _seed_op(
        run_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        target="main.silver.unrelated",
    )
    _seed_value_change(
        run_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        op_id=op_id,
        target="main.silver.orders",
    )
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=main.silver.orders&kind=written")
    assert r.status_code == 200, r.text
    ids = {run["id"] for run in r.json()["runs"]}
    assert "dddddddd-dddd-dddd-dddd-dddddddddddd" in ids


@pytest.mark.asyncio
async def test_kind_read_via_query_history_table() -> None:
    """A run whose query_history referenced the FQN surfaces under kind=read."""
    _seed_run(run_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", tables=[])
    _seed_query_with_table(
        run_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        full_name="main.silver.orders",
    )
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=main.silver.orders&kind=read")
    assert r.status_code == 200, r.text
    ids = {run["id"] for run in r.json()["runs"]}
    assert "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee" in ids


@pytest.mark.asyncio
async def test_kind_read_does_not_match_touched_only_run() -> None:
    """Touched-only run doesn't bleed into kind=read."""
    _seed_run(
        run_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
        tables=["main.silver.orders"],
    )
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=main.silver.orders&kind=read")
    assert r.status_code == 200
    ids = {run["id"] for run in r.json()["runs"]}
    assert "ffffffff-ffff-ffff-ffff-ffffffffffff" not in ids


@pytest.mark.asyncio
async def test_unknown_kind_returns_422() -> None:
    """A garbage ``kind`` value rejects with 422."""
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=main.x.y&kind=nope")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_empty_fqn_returns_422() -> None:
    """A whitespace-only fqn rejects with 422."""
    async with _admin_client() as c:
        r = await c.get("/api/audit/by-table?fqn=%20%20")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_html_by_table_page_renders() -> None:
    """``GET /audit/by-table/main.silver.orders`` returns the page shell."""
    async with _admin_client() as c:
        r = await c.get("/audit/by-table/main.silver.orders")
    assert r.status_code == 200, r.text
    assert "main.silver.orders" in r.text
    assert "Runs that touched" in r.text


@pytest.mark.asyncio
async def test_table_detail_cross_link_route_reachable() -> None:
    """The route the catalog table-detail page links to is reachable."""
    async with _admin_client() as c:
        r = await c.get("/audit/by-table/main.silver.orders")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_pagination_limit_respected() -> None:
    """``limit=1`` returns at most one run."""
    for i in range(3):
        _seed_run(
            run_id=f"limit-{i:01d}-{'0' * 30}"[:36],
            tables=["main.silver.orders"],
        )
    async with _admin_client() as c:
        r = await c.get(
            "/api/audit/by-table?fqn=main.silver.orders&kind=touched&limit=1"
        )
    assert r.status_code == 200
    assert len(r.json()["runs"]) == 1
