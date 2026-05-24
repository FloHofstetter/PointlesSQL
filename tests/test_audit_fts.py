"""SQLite FTS5 audit-lake search.

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
    result = audit_fts.search(app.state.session_factory, query="alice", axis="runs", limit=10)
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
    result = audit_fts.search(app.state.session_factory, query="silver_pii", axis="runs")
    assert result["available"]
    assert any(r["entity_id"] == "22222222-2222-2222-2222-222222222222" for r in result["results"])


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
    result = audit_fts.search(app.state.session_factory, query="finn_distinctive_error", axis="all")
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
        session.query(AgentRun).filter_by(id="77777777-7777-7777-7777-777777777777").delete()
        session.commit()
    after = audit_fts.search(factory, query="gina")
    assert all(r["entity_id"] != "77777777-7777-7777-7777-777777777777" for r in after["results"])


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
    result = audit_fts.search(app.state.session_factory, query="hugo)foo*", axis="runs")
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
async def test_api_audit_search_route(fts_index: None, admin_client: httpx.AsyncClient) -> None:
    """``GET /api/audit/search`` returns the FTS payload."""
    _seed_run(
        run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        principal="jay@example.com",
        tables=["main.bronze.t"],
        notebook="jay/job.py",
    )
    r = await admin_client.get("/api/audit/search?q=jay&axis=runs")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["available"] is True
    assert payload["total_count"] >= 1


@pytest.mark.asyncio
async def test_api_audit_search_empty_query_validation(admin_client: httpx.AsyncClient) -> None:
    """``q=`` empty triggers FastAPI's min_length validator."""
    r = await admin_client.get("/api/audit/search?q=")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_api_audit_search_html_renders(
    fts_index: None, admin_client: httpx.AsyncClient
) -> None:
    """``GET /audit/search`` renders the search page shell."""
    r = await admin_client.get("/audit/search")
    assert r.status_code == 200, r.text
    assert "audit cockpit" in r.text.lower() or "search" in r.text.lower()


@pytest.mark.asyncio
async def test_api_audit_search_no_fts_returns_unavailable(admin_client: httpx.AsyncClient) -> None:
    """Without install_index, the route returns available=false instead of 500."""
    r = await admin_client.get("/api/audit/search?q=anything")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_search_offset_pages_results(fts_index: None) -> None:
    """``offset`` shifts the page; ``next_offset`` reports tail-state.

    Uses a notebook-path token shared across three seeded runs.
    The FTS tokenizer treats ``.``/``_``/``-`` as separators on top of
    unicode61's default punctuation handling, so a single bareword
    like ``pagertestseed`` survives intact and matches all three.
    """
    for i in range(3):
        _seed_run(
            run_id=f"55555555-5555-5555-5555-{i:012d}",
            principal=f"alice{i}@example.com",
            tables=["main.bronze.t"],
            notebook=f"pagertestseed-{i}.py",
        )
    page0 = audit_fts.search(
        app.state.session_factory,
        query="pagertestseed",
        axis="runs",
        limit=2,
        offset=0,
    )
    assert page0["available"]
    assert page0["total_count"] == 2
    assert page0["offset"] == 0
    assert page0["next_offset"] == 2
    page1 = audit_fts.search(
        app.state.session_factory,
        query="pagertestseed",
        axis="runs",
        limit=2,
        offset=2,
    )
    assert page1["total_count"] == 1
    assert page1["offset"] == 2
    assert page1["next_offset"] is None
    seen = {row["entity_id"] for row in page0["results"]} | {
        row["entity_id"] for row in page1["results"]
    }
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_api_audit_search_offset_route(
    fts_index: None, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/audit/search?offset=N`` carries the new pager fields."""
    for i in range(2):
        _seed_run(
            run_id=f"66666666-6666-6666-6666-{i:012d}",
            principal=f"bob{i}@example.com",
            tables=["main.bronze.t"],
            notebook=f"routepager-{i}.py",
        )
    r = await admin_client.get(
        "/api/audit/search?q=routepager&axis=runs&limit=1&offset=1"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offset"] == 1
    assert "next_offset" in body


# ---------------------------------------------------------------------------
# full body + entity_kind filtering
# ---------------------------------------------------------------------------


def test_search_finds_full_body_beyond_140_chars(fts_index: None) -> None:
    """A long comment-body keyword lands in FTS even past the preview cutoff.

    Phase-78 polish: audit-mirror callers now ship the full
    ``body_md`` in their detail JSON alongside the historical
    140-char ``body_preview``.  This test seeds an audit_log row
    whose detail JSON carries a marker keyword more than 200
    characters into the body and confirms FTS surfaces it via
    ``/api/audit/search``.
    """
    long_body_filler = "filler " * 50  # well past the 140-char cutoff
    marker = "phase78MarkerXYZ"
    detail = json.dumps(
        {
            "comment_id": 999,
            "body_preview": long_body_filler[:140],
            "body_md": long_body_filler + marker,
        }
    )
    _seed_audit_log(
        action="audit.discussion.posted",
        target="dp:main.gold#tab-discussion-comment-999",
        detail=detail,
    )
    result = audit_fts.search(
        app.state.session_factory, query=marker, axis="audit_log"
    )
    assert result["available"]
    assert result["total_count"] >= 1
    assert any(marker in (r["snippet"] or "") for r in result["results"])


def test_search_kind_filter_narrows_to_audit_log_axis(fts_index: None) -> None:
    """``?kind=table`` returns only audit_log rows with that kind."""
    _seed_audit_log(
        action="audit.discussion.posted",
        target="table:main.silver.t#tab-discussion-comment-1",
        detail='{"kindfilter78token": true}',
    )
    _seed_audit_log(
        action="audit.discussion.posted",
        target="dp:main.gold#tab-discussion-comment-2",
        detail='{"kindfilter78token": true}',
    )
    table_only = audit_fts.search(
        app.state.session_factory,
        query="kindfilter78token",
        axis="audit_log",
        kind="table",
    )
    assert table_only["available"]
    assert table_only["total_count"] == 1
    assert table_only["results"][0]["entity_kind"] == "table"


def test_search_kind_dp_matches_legacy_data_product_prefix(fts_index: None) -> None:
    """``kind='dp'`` matches both new ``dp:`` and legacy ``data_product:``."""
    _seed_audit_log(
        action="audit.review.posted",
        target="data_product:main.legacy#tab-reviews-1",
        detail='{"legacyMarker78": true}',
    )
    _seed_audit_log(
        action="audit.review.posted",
        target="dp:main.modern#tab-reviews-1",
        detail='{"legacyMarker78": true}',
    )
    dp_only = audit_fts.search(
        app.state.session_factory,
        query="legacyMarker78",
        axis="audit_log",
        kind="dp",
    )
    assert dp_only["available"]
    # Both rows count as kind=dp — the legacy ``data_product:``
    # prefix is normalized to ``dp`` at index time.
    kinds = {r["entity_kind"] for r in dp_only["results"]}
    assert kinds == {"dp"}
    assert dp_only["total_count"] == 2


def test_search_response_carries_kind_field(fts_index: None) -> None:
    """``search()`` echoes the ``kind`` arg in the response envelope."""
    out = audit_fts.search(
        app.state.session_factory,
        query="phase78NoMatch",
        axis="audit_log",
        kind="model",
    )
    assert out["kind"] == "model"
    # No-match path still echoes; the field is contract-stable.
    assert "results" in out
