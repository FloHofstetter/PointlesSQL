"""Tests for the Sprint 13.9 run-scoped query-history surface."""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRun, QueryHistory
from pointlessql.services import query_history as query_history_service


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _create_run(run_id: str) -> str:
    """Insert an :class:`AgentRun` fixture row."""
    factory = app.state.session_factory
    with factory() as session:
        row = AgentRun(
            id=run_id,
            principal=None,
            agent_id="t",
            notebook_path="demo/x.py",
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(row)
        session.commit()
    return run_id


# ---------------------------------------------------------------------------
# record_query persists agent_run_id
# ---------------------------------------------------------------------------


def test_record_query_persists_agent_run_id() -> None:
    factory = app.state.session_factory
    run_id = _create_run("12345678-1234-1234-1234-123456789012")
    started = datetime.datetime.now(datetime.UTC)
    qid = query_history_service.record_query(
        factory,
        user_id=1,
        user_email="t@test.com",
        sql_text="SELECT 1",
        started_at=started,
        finished_at=started,
        status="succeeded",
        row_count=1,
        duration_ms=1,
        referenced_tables=[],
        agent_run_id=run_id,
    )
    with factory() as session:
        row = session.get(QueryHistory, qid)
        assert row is not None
        assert row.agent_run_id == run_id


def test_record_query_drops_garbage_run_id(caplog) -> None:
    factory = app.state.session_factory
    started = datetime.datetime.now(datetime.UTC)
    qid = query_history_service.record_query(
        factory,
        user_id=1,
        user_email="t@test.com",
        sql_text="SELECT 1",
        started_at=started,
        finished_at=started,
        status="succeeded",
        row_count=1,
        duration_ms=1,
        referenced_tables=[],
        agent_run_id="not-a-uuid",
    )
    with factory() as session:
        row = session.get(QueryHistory, qid)
        assert row is not None
        assert row.agent_run_id is None


def test_list_queries_filters_by_agent_run_id() -> None:
    factory = app.state.session_factory
    run_id = _create_run("23456789-2345-2345-2345-234567890123")
    other = _create_run("34567890-3456-3456-3456-345678901234")
    started = datetime.datetime.now(datetime.UTC)
    for tag, sql in (
        (run_id, "SELECT 1"),
        (run_id, "SELECT 2"),
        (other, "SELECT 3"),
        (None, "SELECT 4"),
    ):
        query_history_service.record_query(
            factory,
            user_id=1,
            user_email="t@test.com",
            sql_text=sql,
            started_at=started,
            finished_at=started,
            status="succeeded",
            row_count=1,
            duration_ms=1,
            referenced_tables=[],
            agent_run_id=tag,
        )
    rows = query_history_service.list_queries(factory, agent_run_id=run_id)
    assert {r["sql_text"] for r in rows} == {"SELECT 1", "SELECT 2"}
    assert all(r["agent_run_id"] == run_id for r in rows)


# ---------------------------------------------------------------------------
# /api/sql/execute reads X-Agent-Run-Id header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sql_execute_tags_history_with_header(monkeypatch) -> None:
    factory = app.state.session_factory
    run_id = _create_run("45678901-4567-4567-4567-456789012345")

    # Stub run_sql_sync so the test doesn't need a real DuckDB context.
    from pointlessql.api import sql_routes as sql_routes_mod
    from pointlessql.pql._types import SQLResult

    fake_result = SQLResult(
        columns=[{"name": "x", "type": "BIGINT"}],
        rows=[[1]],
        row_count=1,
        truncated=False,
        duration_ms=1,
        executed_sql="SELECT 1",
        rewritten_sql="SELECT 1",
        referenced_tables=[],
    )
    monkeypatch.setattr(sql_routes_mod, "run_sql_sync", lambda *a, **k: fake_result)

    async with _admin_client() as client:
        response = await client.post(
            "/api/sql/execute",
            json={"sql": "SELECT 1"},
            headers={"X-Agent-Run-Id": run_id},
        )
    assert response.status_code == 200, response.text
    with factory() as session:
        row = session.scalar(
            select(QueryHistory)
            .where(QueryHistory.agent_run_id == run_id)
        )
    assert row is not None
    assert row.sql_text == "SELECT 1"


# ---------------------------------------------------------------------------
# /queries page filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queries_page_filter_by_agent_run_id() -> None:
    factory = app.state.session_factory
    run_id = _create_run("56789012-5678-5678-5678-567890123456")
    started = datetime.datetime.now(datetime.UTC)
    query_history_service.record_query(
        factory,
        user_id=1,
        user_email="t@test.com",
        sql_text="SELECT in_run",
        started_at=started,
        finished_at=started,
        status="succeeded",
        row_count=1,
        duration_ms=1,
        referenced_tables=[],
        agent_run_id=run_id,
    )
    query_history_service.record_query(
        factory,
        user_id=1,
        user_email="t@test.com",
        sql_text="SELECT outside",
        started_at=started,
        finished_at=started,
        status="succeeded",
        row_count=1,
        duration_ms=1,
        referenced_tables=[],
        agent_run_id=None,
    )
    async with _admin_client() as client:
        response = await client.get(f"/queries?agent_run_id={run_id}")
    assert response.status_code == 200
    body = response.text
    assert "SELECT in_run" in body
    assert "SELECT outside" not in body
    assert "Filtered to agent run" in body


# ---------------------------------------------------------------------------
# Run-detail view exposes Queries tab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detail_renders_queries_tab() -> None:
    run_id = "67890123-6789-6789-6789-678901234567"
    factory = app.state.session_factory
    async with _admin_client() as client:
        post = await client.post(
            "/api/agent-runs",
            json={
                "id": run_id,
                "notebook_path": "demo/x.py",
                "source": "import pql\n",
                "runtime_versions": {"python": "3.14.0"},
            },
        )
        assert post.status_code == 200, post.text
        started = datetime.datetime.now(datetime.UTC)
        query_history_service.record_query(
            factory,
            user_id=1,
            user_email="t@test.com",
            sql_text="SELECT visible_in_tab",
            started_at=started,
            finished_at=started,
            status="succeeded",
            row_count=1,
            duration_ms=2,
            referenced_tables=[],
            agent_run_id=run_id,
        )
        page = await client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    body = page.text
    assert 'id="tab-queries-btn"' in body
    assert "SELECT visible_in_tab" in body
