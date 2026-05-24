"""auto-LIMIT injection + Lens cost-gate tests."""

from __future__ import annotations

import pytest

from pointlessql.pql.sql_parser import SQLParseError, inject_limit
from pointlessql.services.lens.cost_gate import (
    LensNonSelectBlockedError,
    LensSessionBudgetExceededError,
    gate_query,
)

# ---------------------------------------------------------------------------
# inject_limit unit tests
# ---------------------------------------------------------------------------


def test_inject_limit_appends_when_missing() -> None:
    """SELECT without LIMIT gains an appended LIMIT clause."""
    out = inject_limit("SELECT * FROM main.silver.t", default_limit=1000)
    assert "LIMIT 1000" in out


def test_inject_limit_preserves_user_limit() -> None:
    """SELECT LIMIT 50 stays at LIMIT 50 even with default 1000."""
    out = inject_limit("SELECT * FROM main.silver.t LIMIT 50", default_limit=1000)
    assert "LIMIT 50" in out
    assert "LIMIT 1000" not in out


def test_inject_limit_user_override_above_default() -> None:
    """User-supplied LIMIT 5000 wins over default 1000."""
    out = inject_limit("SELECT * FROM main.silver.t LIMIT 5000", default_limit=1000)
    assert "LIMIT 5000" in out


def test_inject_limit_idempotent() -> None:
    """Calling inject_limit twice produces the same SQL."""
    once = inject_limit("SELECT * FROM main.silver.t", default_limit=1000)
    twice = inject_limit(once, default_limit=1000)
    assert once == twice


def test_inject_limit_handles_with_cte() -> None:
    """``WITH ... SELECT`` gets the LIMIT on the outer SELECT."""
    out = inject_limit("WITH a AS (SELECT 1 x) SELECT * FROM a", default_limit=42)
    assert "LIMIT 42" in out


def test_inject_limit_rejects_insert() -> None:
    """INSERT statement raises SQLParseError (Lens is read-only)."""
    with pytest.raises(SQLParseError):
        inject_limit("INSERT INTO main.silver.t VALUES (1)")


def test_inject_limit_rejects_delete() -> None:
    """DELETE statement raises SQLParseError."""
    with pytest.raises(SQLParseError):
        inject_limit("DELETE FROM main.silver.t WHERE id = 1")


def test_inject_limit_clamps_non_positive_default() -> None:
    """A non-positive default_limit is clamped to 1."""
    out = inject_limit("SELECT * FROM main.silver.t", default_limit=0)
    assert "LIMIT 1" in out


# ---------------------------------------------------------------------------
# gate_query unit tests
# ---------------------------------------------------------------------------


def test_gate_query_returns_gated_sql_for_select() -> None:
    """Happy path: SELECT passes through with auto-LIMIT injected."""
    gated = gate_query(
        "SELECT * FROM main.silver.t",
        approved_tables={},
        default_limit=500,
        max_query_cost=1_000_000.0,
        max_session_cost=10_000_000.0,
        session_cost_so_far=0.0,
    )
    assert "LIMIT 500" in gated.sql
    assert gated.cost.cost == 0  # no approved tables → cost 0


def test_gate_query_blocks_non_select() -> None:
    """INSERT input → LensNonSelectBlockedError."""
    with pytest.raises(LensNonSelectBlockedError):
        gate_query(
            "INSERT INTO main.silver.t VALUES (1)",
            approved_tables={},
            default_limit=1000,
            max_query_cost=1_000_000.0,
            max_session_cost=10_000_000.0,
            session_cost_so_far=0.0,
        )


def test_gate_query_session_budget_exceeded() -> None:
    """Session over-budget → LensSessionBudgetExceededError, even at zero cost."""
    # When approved_tables is empty cost is 0; force the budget cap to be
    # already exceeded so the predicate ``session_cost_so_far + 0 > cap``
    # triggers.  Use cap=0 with session_cost_so_far=10 to enter the deny
    # branch.
    with pytest.raises(LensSessionBudgetExceededError):
        gate_query(
            "SELECT * FROM main.silver.t",
            approved_tables={},
            default_limit=1000,
            max_query_cost=1_000_000.0,
            max_session_cost=0.0,
            session_cost_so_far=10.0,
        )


# ---------------------------------------------------------------------------
# query tool integration (audit-hook + cost-gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_tool_returns_gated_sql_in_audit_row() -> None:
    """Tool dispatch persists a tool-row carrying the gated SQL."""
    import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from pointlessql.config import Settings
    from pointlessql.models import Base, LensSession, User, Workspace
    from pointlessql.services.lens import list_session_messages
    from pointlessql.services.lens.tools import (
        SessionContext,
        execute_tool_with_audit,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(Workspace(id=1, slug="d", name="d", created_at=now))
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
        s.flush()
        sess = LensSession(
            workspace_id=1,
            owner_id=1,
            title="cost-gate",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            total_cost_estimate=0.0,
            created_at=now,
            updated_at=now,
        )
        s.add(sess)
        s.commit()
        sid = int(sess.id)

    ctx = SessionContext(
        workspace_id=1,
        user_id=1,
        lens_session_id=sid,
        factory=factory,
        settings=Settings(),
        uc_client=None,
    )
    out = await execute_tool_with_audit(
        tool_name="query",
        ctx=ctx,
        raw_args={"sql": "SELECT 1 FROM main.silver.t"},
    )
    assert "LIMIT" in out["executed_sql"].upper()

    msgs = list_session_messages(factory, session_id=sid)
    assert any(m.tool_name == "query" and m.tool_status == "ok" for m in msgs)
