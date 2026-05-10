"""Sprint 65.2 — Lens tool registry tests.

Exercise the registry shape, audit-hook dispatch, schema converters,
and one happy-path tool execution per category.  Uses synthetic
:class:`SessionContext` with ``uc_client=None`` for catalog tools and
direct DB seeding for lineage tools.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.config import Settings
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LensSession,
    LineageRowEdge,
    User,
    Workspace,
)
from pointlessql.services.lens.tools import (
    ALL_TOOLS,
    LensToolError,
    SessionContext,
    UnknownLensToolError,
    execute_tool_with_audit,
    get_tool,
    list_tool_names,
    to_anthropic_schemas,
    to_mcp_schemas,
    to_openai_schemas,
)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """Build an in-memory SQLite session factory + seed minimal users."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    f = sessionmaker(bind=engine)
    now = datetime.datetime.now(datetime.UTC)
    with f() as s:
        s.add(
            Workspace(
                id=1,
                slug="default",
                name="Default",
                created_at=now,
            )
        )
        s.add(
            User(
                id=1,
                email="t@t",
                display_name="T",
                password_hash="x",
                is_admin=False,
                created_at=now,
            )
        )
        s.commit()
    return f


@pytest.fixture
def lens_session_id(factory) -> int:  # type: ignore[no-untyped-def]
    """Create one Lens session and return its id."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        row = LensSession(
            workspace_id=1,
            owner_id=1,
            title="tool-test",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            total_cost_estimate=0.0,
            created_at=now,
            updated_at=now,
        )
        s.add(row)
        s.commit()
        return int(row.id)


@pytest.fixture
def ctx(factory, lens_session_id) -> SessionContext:  # type: ignore[no-untyped-def]
    """Build a SessionContext suitable for tool execution."""
    return SessionContext(
        workspace_id=1,
        user_id=1,
        lens_session_id=lens_session_id,
        factory=factory,
        settings=Settings(),
        uc_client=None,
    )


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_registry_lists_expected_tools() -> None:
    """Sprint 65.2 ships six tools."""
    names = list_tool_names()
    assert {
        "list_catalogs",
        "list_schemas",
        "list_tables",
        "describe_table",
        "lineage_neighbors",
        "provenance",
    } <= set(names)


def test_get_tool_returns_def_or_none() -> None:
    """Lookup hits known tools, returns None on miss."""
    assert get_tool("provenance") is not None
    assert get_tool("does_not_exist") is None


def test_openai_schema_shape() -> None:
    """OpenAI converter wraps each tool in {type:function, function:{...}}."""
    schemas = to_openai_schemas(ALL_TOOLS)
    assert all(s["type"] == "function" for s in schemas)
    assert all("name" in s["function"] and "parameters" in s["function"] for s in schemas)


def test_anthropic_schema_shape() -> None:
    """Anthropic converter emits {name, description, input_schema}."""
    schemas = to_anthropic_schemas(ALL_TOOLS)
    assert all({"name", "description", "input_schema"} <= set(s) for s in schemas)


def test_mcp_schema_shape() -> None:
    """MCP converter emits {name, description, inputSchema} (camelCase)."""
    schemas = to_mcp_schemas(ALL_TOOLS)
    assert all({"name", "description", "inputSchema"} <= set(s) for s in schemas)


# ---------------------------------------------------------------------------
# Audit-hook dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_hook_writes_lens_message_on_success(ctx) -> None:  # type: ignore[no-untyped-def]
    """Successful dispatch persists a tool-row + bumps session activity."""
    # Use list_catalogs against ctx with uc_client=None — returns empty result
    result = await execute_tool_with_audit(
        tool_name="list_catalogs", ctx=ctx, raw_args={}
    )
    assert "catalogs" in result

    # Verify the lens_messages row landed
    from pointlessql.services.lens import list_session_messages

    msgs = list_session_messages(ctx.factory, session_id=ctx.lens_session_id)
    assert any(m.tool_name == "list_catalogs" and m.tool_status == "ok" for m in msgs)


@pytest.mark.asyncio
async def test_audit_hook_writes_error_on_unknown_tool(ctx) -> None:  # type: ignore[no-untyped-def]
    """Unknown tool name → audit row + UnknownLensToolError."""
    with pytest.raises(UnknownLensToolError):
        await execute_tool_with_audit(
            tool_name="grok_query", ctx=ctx, raw_args={}
        )

    from pointlessql.services.lens import list_session_messages

    msgs = list_session_messages(ctx.factory, session_id=ctx.lens_session_id)
    assert any(m.tool_name == "grok_query" and m.tool_status == "error" for m in msgs)


@pytest.mark.asyncio
async def test_audit_hook_validates_args(ctx) -> None:  # type: ignore[no-untyped-def]
    """Bad input args → LensToolError with validation detail."""
    with pytest.raises(LensToolError):
        await execute_tool_with_audit(
            tool_name="describe_table",
            ctx=ctx,
            raw_args={"table_fqn": ""},  # below min_length=3
        )


# ---------------------------------------------------------------------------
# Tool happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provenance_tool_returns_trace(ctx) -> None:  # type: ignore[no-untyped-def]
    """Provenance tool returns a populated ProvenanceTrace."""
    # Seed one row edge
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with ctx.factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="t",
                agent_id="t",
                notebook_path="n",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.t",
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        s.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op.id,
                source_table="main.bronze.t",
                source_row_id="b1",
                target_table="main.silver.t",
                target_row_id="s1",
                created_at=now,
            )
        )
        s.commit()

    result = await execute_tool_with_audit(
        tool_name="provenance",
        ctx=ctx,
        raw_args={"table_fqn": "main.silver.t", "row_id": "s1"},
    )
    assert result["mode"] == "row"
    assert any(s["table_fqn"] == "main.bronze.t" for s in result["sources"])


@pytest.mark.asyncio
async def test_lineage_neighbors_tool(ctx) -> None:  # type: ignore[no-untyped-def]
    """lineage_neighbors returns distinct upstream + downstream tables."""
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with ctx.factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="t",
                agent_id="t",
                notebook_path="n",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.t",
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        s.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op.id,
                source_table="main.bronze.a",
                source_row_id="x",
                target_table="main.silver.t",
                target_row_id="y",
                created_at=now,
            )
        )
        s.commit()

    result = await execute_tool_with_audit(
        tool_name="lineage_neighbors",
        ctx=ctx,
        raw_args={"table_fqn": "main.silver.t"},
    )
    assert "main.bronze.a" in result["upstream"]


@pytest.mark.asyncio
async def test_list_catalogs_with_no_uc_client_returns_empty(ctx) -> None:  # type: ignore[no-untyped-def]
    """When uc_client is None the catalog tools fall back gracefully."""
    result = await execute_tool_with_audit(
        tool_name="list_catalogs", ctx=ctx, raw_args={}
    )
    assert result == {"catalogs": []}
