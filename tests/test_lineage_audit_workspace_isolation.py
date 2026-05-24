"""workspace isolation for lineage / audit_log / governance / queries.

Asserts that every audit-side table that grew workspace_id in 28.1b
isolates correctly:

* lineage_row_edges / row_rejects / column_map / value_changes
* query_history / query_history_tables
* audit_log
* governance_events
* unattributed_writes (UNIQUE constraint widened to
  (workspace_id, table_fqn, delta_version))
* anomaly_acks (UNIQUE constraint widened to prefix workspace_id)
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models import (
    AnomalyAck,
    AuditLog,
    GovernanceEvent,
    LineageRowEdge,
    QueryHistory,
    UnattributedWrite,
)
from pointlessql.services import audit as audit_service
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


@pytest.fixture
def two_workspaces() -> tuple[int, int]:
    a = workspaces_service.create_workspace(_factory(), slug="ws-i", name="Iso A")
    b = workspaces_service.create_workspace(_factory(), slug="ws-j", name="Iso B")
    return a.id, b.id


# ---------------------------------------------------------------------------
# Schema sanity — every Sprint-28.1b table grew workspace_id
# ---------------------------------------------------------------------------


def test_28_1b_columns_exist() -> None:
    from sqlalchemy import inspect

    insp = inspect(_factory()().get_bind())
    for table in (
        "lineage_row_edges",
        "lineage_row_rejects",
        "lineage_column_map",
        "lineage_value_changes",
        "query_history",
        "query_history_tables",
        "audit_log",
        "governance_events",
        "unattributed_writes",
        "anomaly_acks",
    ):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "workspace_id" in cols, f"{table} missing workspace_id column"


# ---------------------------------------------------------------------------
# audit.log_action threads workspace_id
# ---------------------------------------------------------------------------


def test_log_action_writes_workspace_id(two_workspaces: tuple[int, int]) -> None:
    ws_a, ws_b = two_workspaces
    audit_service.log_action(
        _factory(),
        user_id=0,
        user_email="cli@example.com",
        action="cli.test",
        target="thing:1",
        workspace_id=ws_a,
    )
    audit_service.log_action(
        _factory(),
        user_id=0,
        user_email="cli@example.com",
        action="cli.test",
        target="thing:2",
        workspace_id=ws_b,
    )
    with _factory()() as session:
        rows_a = session.query(AuditLog).filter(AuditLog.workspace_id == ws_a).count()
        rows_b = session.query(AuditLog).filter(AuditLog.workspace_id == ws_b).count()
        assert rows_a >= 1
        assert rows_b >= 1


def test_log_action_defaults_to_workspace_one() -> None:
    audit_service.log_action(
        _factory(),
        user_id=0,
        user_email="default@example.com",
        action="cli.default",
        target="thing:default",
    )
    with _factory()() as session:
        row = (
            session.query(AuditLog)
            .filter(AuditLog.action == "cli.default")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert int(row.workspace_id) == 1


# ---------------------------------------------------------------------------
# query_history workspace_id passthrough
# ---------------------------------------------------------------------------


def test_record_query_writes_workspace_id(two_workspaces: tuple[int, int]) -> None:
    from pointlessql.services import query_history as qh

    ws_a, _ = two_workspaces
    now = datetime.datetime.now(datetime.UTC)
    new_id = qh.record_query(
        _factory(),
        user_id=1,
        user_email="alice@example.com",
        sql_text="SELECT 1",
        started_at=now,
        finished_at=now,
        status="succeeded",
        row_count=1,
        duration_ms=2,
        referenced_tables=[],
        workspace_id=ws_a,
    )
    with _factory()() as session:
        row = session.get(QueryHistory, new_id)
        assert row is not None
        assert int(row.workspace_id) == ws_a


# ---------------------------------------------------------------------------
# anomaly_acks: workspace_id widens UNIQUE constraint
# ---------------------------------------------------------------------------


def test_anomaly_ack_unique_includes_workspace(two_workspaces: tuple[int, int]) -> None:
    """Two workspaces can independently ack the same metric bin.

    Uses non-NULL ``group_value`` / ``group_kind`` because SQLite's
    UNIQUE constraint treats NULLs as distinct (so a NULL-bearing
    duplicate would not collide regardless of workspace_id).  The
    cross-workspace pair must succeed, the same-workspace duplicate
    must fail.
    """
    ws_a, ws_b = two_workspaces
    now = datetime.datetime.now(datetime.UTC)
    base: dict[str, Any] = {
        "metric": "rejects",
        "bin_iso": "2026-05-05",
        "bin_kind": "day",
        "group_value": "main.silver.orders",
        "group_kind": "table",
        "acked_by": "admin@example.com",
        "acked_at": now,
        "dismissed_until": None,
        "comment": None,
    }
    with _factory()() as session:
        session.add(AnomalyAck(workspace_id=ws_a, **base))
        session.add(AnomalyAck(workspace_id=ws_b, **base))
        session.commit()
    # A third row for ws_a duplicates the natural identity → IntegrityError.
    with _factory()() as session:
        session.add(AnomalyAck(workspace_id=ws_a, **base))
        with pytest.raises(IntegrityError):
            session.commit()


# ---------------------------------------------------------------------------
# unattributed_writes: workspace_id widens UNIQUE constraint
# ---------------------------------------------------------------------------


def test_unattributed_write_unique_includes_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    """Same (table_fqn, delta_version) can fan out to multiple workspaces."""
    ws_a, ws_b = two_workspaces
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            UnattributedWrite(
                workspace_id=ws_a,
                table_fqn="main.silver.orders",
                delta_version=42,
                detected_at=now,
            )
        )
        session.add(
            UnattributedWrite(
                workspace_id=ws_b,
                table_fqn="main.silver.orders",
                delta_version=42,
                detected_at=now,
            )
        )
        session.commit()
    # Re-adding the same (workspace_id, table_fqn, delta_version) triple fails.
    with _factory()() as session:
        session.add(
            UnattributedWrite(
                workspace_id=ws_a,
                table_fqn="main.silver.orders",
                delta_version=42,
                detected_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


# ---------------------------------------------------------------------------
# lineage_row_edges derives workspace from parent op
# ---------------------------------------------------------------------------


def test_lineage_edges_inherit_workspace_from_op(
    two_workspaces: tuple[int, int],
) -> None:
    """record_edges looks up workspace_id from the parent agent_run_operation."""
    import hashlib
    import uuid

    from pointlessql.models import AgentRun, AgentRunOperation
    from pointlessql.services import lineage_edges as le

    ws_a, _ = two_workspaces
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    sha = hashlib.sha256(b"x").hexdigest()
    with _factory()() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=ws_a,
                principal="alice@example.com",
                notebook_path="x.py",
                source_snapshot_sha=sha,
                status="succeeded",
                started_at=now,
            )
        )
        session.flush()
        op = AgentRunOperation(
            workspace_id=ws_a,
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.x",
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        op_id = int(op.id)

    err = le.record_edges(
        _factory(),
        run_id=run_id,
        op_id=op_id,
        source_table="main.bronze.x",
        target_table="main.silver.x",
        source_row_ids=["r1"],
        target_row_ids=["t1"],
    )
    assert err is None
    with _factory()() as session:
        edge = session.query(LineageRowEdge).filter(LineageRowEdge.op_id == op_id).one()
        assert int(edge.workspace_id) == ws_a


# ---------------------------------------------------------------------------
# governance_events emit threads workspace_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_governance_event_writes_workspace_id(
    two_workspaces: tuple[int, int],
) -> None:
    from pointlessql.services.workspace import governance as ge

    ws_a, _ = two_workspaces
    await ge.emit_governance_event(
        ge.EVENT_TYPE_AUDIT_EXPORT_ISSUED,
        {"foo": "bar"},
        session_factory=_factory(),
        workspace_id=ws_a,
    )
    with _factory()() as session:
        row = session.query(GovernanceEvent).order_by(GovernanceEvent.id.desc()).first()
        assert row is not None
        assert int(row.workspace_id) == ws_a
