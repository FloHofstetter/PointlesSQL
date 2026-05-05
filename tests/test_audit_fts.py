"""Phase 18.7 — SQLite FTS5 audit-lake search.

Test fixtures call :func:`audit_fts.install_index` to create the
``audit_search`` virtual table because conftest's
``Base.metadata.create_all`` doesn't include FTS5 vtables (they
aren't ORM-mapped).  Each test seeds a small set of source rows
across the five axes, then verifies that the triggers populated
the index, that ``search`` returns the expected row, and that
specific FTS5 quirks (UC FQN component matching, snippet
escaping, axis filter) behave as advertised.
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
    AgentRunToolCall,
    AuditLog,
    QueryHistory,
)
from pointlessql.services import audit_fts


@pytest.fixture
def fts_index() -> None:
    """Provision the FTS5 virtual table for the lifetime of the test.

    Conftest tears the schema down between tests, so the trigger
    + vtable scaffolding is rebuilt from scratch each run.  No
    cleanup needed.
    """
    audit_fts.install_index(app.state.session_factory)


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_run(*, run_id: str, principal: str, tables: list[str], notebook: str) -> None:
    """Add a single :class:`AgentRun` row through the SQLAlchemy session."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal=principal,
                agent_id="searcher",
                notebook_path=notebook,
                source_snapshot_sha="0" * 64,
                status="succeeded",
                started_at=dt.datetime.now(dt.UTC),
                tables_touched=json.dumps(tables),
            )
        )
        session.commit()


def _seed_op(*, run_id: str, target: str, error: str | None = None) -> int:
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
            error_message=error,
            started_at=dt.datetime.now(dt.UTC),
            finished_at=dt.datetime.now(dt.UTC),
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return int(op.id)


def _seed_query(*, run_id: str, sql: str, user: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            QueryHistory(
                user_id=1,
                user_email=user,
                sql_text=sql,
                started_at=dt.datetime.now(dt.UTC),
                finished_at=dt.datetime.now(dt.UTC),
                duration_ms=1,
                status="succeeded",
                read_kind="sql_editor",
                agent_run_id=run_id,
            )
        )
        session.commit()


def _seed_tool_call(*, run_id: str, tool: str, args: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRunToolCall(
                agent_run_id=run_id,
                tool_name=tool,
                args_json=args,
                called_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _seed_audit_log(*, action: str, target: str, detail: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AuditLog(
                user_id=1,
                user_email="admin@test.com",
                action=action,
                target=target,
                detail=detail,
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def test_install_index_idempotent(fts_index: None) -> None:
    """Calling install_index twice does not error."""
    second = audit_fts.install_index(app.state.session_factory)
    assert second is False
    assert audit_fts.is_available(app.state.session_factory)


def test_search_runs_axis_finds_principal(fts_index: None) -> None:
    """A run keyed off principal email surfaces in axis=runs."""
    _seed_run(
        run_id="11111111-1111-1111-1111-111111111111",
        principal="alice@example.com",
        tables=["main.silver.orders"],
        notebook="alice/job.py",
    )
    result = audit_fts.search(
        app.state.session_factory, query="alice", axis="runs", limit=10
    )
    assert result["available"] is True
    assert result["total_count"] == 1
    assert result["results"][0]["axis"] == "runs"
    assert result["results"][0]["entity_id"] == "11111111-1111-1111-1111-111111111111"


def test_search_uc_fqn_matches_component(fts_index: None) -> None:
    """Tokenizer splits FQNs on dots so a single component matches."""
    _seed_run(
        run_id="22222222-2222-2222-2222-222222222222",
        principal="bob@example.com",
        tables=["main.silver_pii.orders"],
        notebook="bob/job.py",
    )
    result = audit_fts.search(
        app.state.session_factory, query="silver_pii", axis="runs"
    )
    assert result["available"]
    assert any(
        r["entity_id"] == "22222222-2222-2222-2222-222222222222"
        for r in result["results"]
    )


def test_search_ops_axis_finds_error_message(fts_index: None) -> None:
    """An op with a distinctive error_message is found via the ``ops`` axis."""
    _seed_run(
        run_id="33333333-3333-3333-3333-333333333333",
        principal="carol@example.com",
        tables=["main.silver.orders"],
        notebook="carol/etl.py",
    )
    _seed_op(
        run_id="33333333-3333-3333-3333-333333333333",
        target="main.silver.orders",
        error="schema_mismatch_on_amount",
    )
    result = audit_fts.search(
        app.state.session_factory,
        query="schema_mismatch_on_amount",
        axis="ops",
    )
    assert result["available"]
    assert result["total_count"] == 1
    assert result["results"][0]["axis"] == "ops"


def test_search_queries_axis_finds_sql(fts_index: None) -> None:
    """A SQL string in query_history surfaces under axis=queries."""
    _seed_run(
        run_id="44444444-4444-4444-4444-444444444444",
        principal="dan@example.com",
        tables=["main.bronze.events"],
        notebook="dan/sql.py",
    )
    _seed_query(
        run_id="44444444-4444-4444-4444-444444444444",
        sql="SELECT customer_marker_xyz FROM main.bronze.events",
        user="dan@example.com",
    )
    result = audit_fts.search(
        app.state.session_factory, query="customer_marker_xyz", axis="queries"
    )
    assert result["available"]
    assert result["total_count"] >= 1
    assert any("customer_marker_xyz" in (r["snippet"] or "") for r in result["results"])


def test_search_tool_calls_axis_finds_tool_name(fts_index: None) -> None:
    """A tool call with a distinctive tool_name surfaces under axis=tool_calls."""
    _seed_run(
        run_id="55555555-5555-5555-5555-555555555555",
        principal="eve@example.com",
        tables=[],
        notebook="eve/agent.py",
    )
    _seed_tool_call(
        run_id="55555555-5555-5555-5555-555555555555",
        tool="pql_query_unique_marker",
        args='{"sql": "select 1"}',
    )
    result = audit_fts.search(
        app.state.session_factory,
        query="pql_query_unique_marker",
        axis="tool_calls",
    )
    assert result["available"]
    assert result["total_count"] == 1


def test_search_audit_log_axis_finds_action(fts_index: None) -> None:
    """An audit_log row's action + detail are searchable on axis=audit_log."""
    _seed_audit_log(
        action="custom_marker_action",
        target="catalog:main",
        detail="payload with distinctive_audit_marker",
    )
    result = audit_fts.search(
        app.state.session_factory,
        query="distinctive_audit_marker",
        axis="audit_log",
    )
    assert result["available"]
    assert result["total_count"] == 1


def test_search_all_axis_aggregates(fts_index: None) -> None:
    """``axis=all`` returns matches from multiple axes."""
    _seed_run(
        run_id="66666666-6666-6666-6666-666666666666",
        principal="finn@example.com",
        tables=["main.silver.orders"],
        notebook="finn/spread.py",
    )
    _seed_op(
        run_id="66666666-6666-6666-6666-666666666666",
        target="main.silver.orders",
        error="finn_distinctive_error",
    )
    _seed_query(
        run_id="66666666-6666-6666-6666-666666666666",
        sql="select finn_distinctive_error",
        user="finn@example.com",
    )
    result = audit_fts.search(
        app.state.session_factory, query="finn_distinctive_error", axis="all"
    )
    assert result["available"]
    axes = {r["axis"] for r in result["results"]}
    assert "ops" in axes
    assert "queries" in axes


def test_search_delete_trigger_drops_row(fts_index: None) -> None:
    """Deleting the source row removes it from audit_search via trigger."""
    _seed_run(
        run_id="77777777-7777-7777-7777-777777777777",
        principal="gina@example.com",
        tables=["main.bronze.t"],
        notebook="gina/job.py",
    )
    factory = app.state.session_factory
    before = audit_fts.search(factory, query="gina")
    assert before["total_count"] >= 1
    with factory() as session:
        session.query(AgentRun).filter_by(
            id="77777777-7777-7777-7777-777777777777"
        ).delete()
        session.commit()
    after = audit_fts.search(factory, query="gina")
    assert all(
        r["entity_id"] != "77777777-7777-7777-7777-777777777777"
        for r in after["results"]
    )


def test_search_sanitises_reserved_punctuation(fts_index: None) -> None:
    """Reserved FTS5 punctuation in user input is replaced with space.

    Without sanitisation, ``"foo)bar"`` would crash the MATCH parser
    with a syntax error.
    """
    _seed_run(
        run_id="88888888-8888-8888-8888-888888888888",
        principal="hugo@example.com",
        tables=["main.bronze.t"],
        notebook="hugo/job.py",
    )
    result = audit_fts.search(
        app.state.session_factory, query="hugo)foo*", axis="runs"
    )
    assert result["available"]
    # No exception means sanitisation kicked in.


def test_rebuild_index_re_seeds(fts_index: None) -> None:
    """rebuild_index drops + re-populates the vtable from source tables."""
    _seed_run(
        run_id="99999999-9999-9999-9999-999999999999",
        principal="ivy@example.com",
        tables=["main.bronze.t"],
        notebook="ivy/job.py",
    )
    counts = audit_fts.rebuild_index(app.state.session_factory)
    assert counts["runs"] >= 1


@pytest.mark.asyncio
async def test_api_audit_search_route(fts_index: None) -> None:
    """``GET /api/audit/search`` returns the FTS payload."""
    _seed_run(
        run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        principal="jay@example.com",
        tables=["main.bronze.t"],
        notebook="jay/job.py",
    )
    async with _admin_client() as c:
        r = await c.get("/api/audit/search?q=jay&axis=runs")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["available"] is True
    assert payload["total_count"] >= 1


@pytest.mark.asyncio
async def test_api_audit_search_empty_query_validation() -> None:
    """``q=`` empty triggers FastAPI's min_length validator."""
    async with _admin_client() as c:
        r = await c.get("/api/audit/search?q=")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_api_audit_search_html_renders(fts_index: None) -> None:
    """``GET /audit/search`` renders the search page shell."""
    async with _admin_client() as c:
        r = await c.get("/audit/search")
    assert r.status_code == 200, r.text
    assert "audit cockpit" in r.text.lower() or "search" in r.text.lower()


@pytest.mark.asyncio
async def test_api_audit_search_no_fts_returns_unavailable() -> None:
    """Without install_index, the route returns available=false instead of 500."""
    async with _admin_client() as c:
        r = await c.get("/api/audit/search?q=anything")
    assert r.status_code == 200
    assert r.json()["available"] is False
