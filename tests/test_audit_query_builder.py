"""Behavioural tests for the cockpit SQL aggregation foundation.

These pin the per-metric :class:`MetricSpec` (table, columns, filter,
measure), the dialect-correct time-bucketing in :func:`bin_expr`, and
the AND-ed filter assembly in :func:`apply_audit_filters` by compiling
the resulting SQLAlchemy expressions to text.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunToolCall,
    LineageRowReject,
    LineageValueChange,
    QueryHistory,
    UnattributedWrite,
)
from pointlessql.services.audit_aggregator._query_builder import (
    VALID_BINS,
    VALID_GROUP_BY,
    VALID_METRICS,
    apply_audit_filters,
    bin_expr,
    metric_spec,
)


def _sql(expr: object) -> str | None:
    if expr is None:
        return None
    return str(expr.compile(compile_kwargs={"literal_binds": True}))


_EXPECTED: dict[str, dict[str, object]] = {
    "runs": dict(
        table=AgentRun,
        ts=AgentRun.started_at,
        target=None,
        runid=AgentRun.id,
        where=None,
        measure="count(agent_runs.id)",
    ),
    "ops": dict(
        table=AgentRunOperation,
        ts=AgentRunOperation.started_at,
        target=AgentRunOperation.target_table,
        runid=AgentRunOperation.agent_run_id,
        where=None,
        measure="count(agent_run_operations.id)",
    ),
    "errored_ops": dict(
        table=AgentRunOperation,
        ts=AgentRunOperation.started_at,
        target=AgentRunOperation.target_table,
        runid=AgentRunOperation.agent_run_id,
        where="agent_run_operations.error_message IS NOT NULL",
        measure="count(agent_run_operations.id)",
    ),
    "rows_written": dict(
        table=AgentRunOperation,
        ts=AgentRunOperation.started_at,
        target=AgentRunOperation.target_table,
        runid=AgentRunOperation.agent_run_id,
        where="agent_run_operations.op_name IN ('merge', 'write_table')",
        measure="coalesce(sum(agent_run_operations.rows_affected), 0)",
    ),
    "value_changes": dict(
        table=LineageValueChange,
        ts=LineageValueChange.created_at,
        target=LineageValueChange.target_table,
        runid=LineageValueChange.run_id,
        where=None,
        measure="count(lineage_value_changes.id)",
    ),
    "rejects": dict(
        table=LineageRowReject,
        ts=LineageRowReject.created_at,
        target=LineageRowReject.source_table,
        runid=LineageRowReject.run_id,
        where=None,
        measure="count(lineage_row_rejects.id)",
    ),
    "expectation_failures": dict(
        table=LineageRowReject,
        ts=LineageRowReject.created_at,
        target=LineageRowReject.source_table,
        runid=LineageRowReject.run_id,
        where="lineage_row_rejects.reason = 'expectation_failed'",
        measure="count(lineage_row_rejects.id)",
    ),
    "external_writes": dict(
        table=UnattributedWrite,
        ts=UnattributedWrite.detected_at,
        target=UnattributedWrite.table_fqn,
        runid=None,
        where=None,
        measure="count(unattributed_writes.id)",
    ),
    "cost_denials": dict(
        table=AgentRun,
        ts=AgentRun.started_at,
        target=None,
        runid=AgentRun.id,
        where="agent_runs.status = 'denied' AND agent_runs.cost_gate_trigger IS NOT NULL",
        measure="count(agent_runs.id)",
    ),
    "tool_calls": dict(
        table=AgentRunToolCall,
        ts=AgentRunToolCall.called_at,
        target=None,
        runid=AgentRunToolCall.agent_run_id,
        where=None,
        measure="count(agent_run_tool_calls.id)",
    ),
    "queries": dict(
        table=QueryHistory,
        ts=QueryHistory.started_at,
        target=None,
        runid=QueryHistory.agent_run_id,
        where=None,
        measure="count(query_history.id)",
    ),
}


def test_expected_table_covers_every_valid_metric() -> None:
    assert set(_EXPECTED) == VALID_METRICS
    assert len(VALID_METRICS) == 11


@pytest.mark.parametrize("metric", sorted(_EXPECTED))
def test_metric_spec_fields(metric: str) -> None:
    exp = _EXPECTED[metric]
    spec = metric_spec(metric)  # type: ignore[arg-type]
    assert spec.table is exp["table"]
    assert spec.timestamp_col is exp["ts"]
    assert spec.target_col is exp["target"]
    assert spec.run_id_col is exp["runid"]
    assert spec.requires_run_join is False
    assert _sql(spec.where) == exp["where"]
    assert _sql(spec.measure) == exp["measure"]


def test_valid_constant_sets() -> None:
    assert VALID_BINS == frozenset({"hour", "day", "week"})
    assert VALID_GROUP_BY == frozenset({"none", "table", "principal"})


# --- bin_expr -------------------------------------------------------------


@pytest.mark.parametrize(
    "dialect,bin_,expected",
    [
        ("sqlite", "hour", "strftime('%Y-%m-%d %H:00', agent_runs.started_at)"),
        ("sqlite", "day", "strftime('%Y-%m-%d', agent_runs.started_at)"),
        ("sqlite", "week", "strftime('%Y-%W', agent_runs.started_at)"),
        ("postgresql", "hour", "CAST(date_trunc('hour', agent_runs.started_at) AS VARCHAR)"),
        ("postgresql", "day", "CAST(date_trunc('day', agent_runs.started_at) AS VARCHAR)"),
        ("postgresql", "week", "CAST(date_trunc('week', agent_runs.started_at) AS VARCHAR)"),
        # dialect_name.startswith("postgres") — bare "postgres" also routes
        # to the date_trunc branch.
        ("postgres", "hour", "CAST(date_trunc('hour', agent_runs.started_at) AS VARCHAR)"),
    ],
)
def test_bin_expr(dialect: str, bin_: str, expected: str) -> None:
    assert _sql(bin_expr(AgentRun.started_at, bin_, dialect)) == expected  # type: ignore[arg-type]


# --- apply_audit_filters --------------------------------------------------


def _filtered(metric: str, **kw: object) -> str:
    spec = metric_spec(metric)  # type: ignore[arg-type]
    kw.setdefault("since", None)
    kw.setdefault("until", None)
    kw.setdefault("principal", None)
    kw.setdefault("agent_id", None)
    kw.setdefault("table", None)
    stmt = apply_audit_filters(select(spec.measure), spec, **kw)  # type: ignore[arg-type]
    return _sql(stmt) or ""


def test_filter_since_is_inclusive_lower_bound() -> None:
    sql = _filtered("ops", since=datetime.datetime(2026, 1, 1))
    assert "agent_run_operations.started_at >= '2026-01-01" in sql


def test_filter_until_is_exclusive_upper_bound() -> None:
    sql = _filtered("ops", until=datetime.datetime(2026, 2, 1))
    assert "agent_run_operations.started_at < '2026-02-01" in sql


def test_filter_spec_where_is_applied() -> None:
    sql = _filtered("errored_ops")
    assert "error_message IS NOT NULL" in sql


def test_filter_table_uses_target_col_for_op_metrics() -> None:
    sql = _filtered("ops", table="cat.sch.t")
    assert "agent_run_operations.target_table = 'cat.sch.t'" in sql


def test_filter_table_blank_is_ignored() -> None:
    sql = _filtered("ops", table="   ")
    assert "target_table" not in sql


def test_filter_table_on_run_metric_uses_tables_touched_like() -> None:
    sql = _filtered("runs", table="cat.sch.t")
    assert "tables_touched" in sql
    assert "'%\"cat.sch.t\"%'" in sql


def test_filter_principal_joins_agent_run_for_op_metric() -> None:
    sql = _filtered("ops", principal="alice")
    assert "JOIN agent_runs" in sql
    assert "agent_runs.principal = 'alice'" in sql


def test_filter_agent_id_filters_on_agent_run() -> None:
    sql = _filtered("runs", agent_id="bot-7")
    assert "agent_runs.agent_id = 'bot-7'" in sql


def test_filter_principal_on_external_writes_returns_empty() -> None:
    # No run linkage -> WHERE false so the caller sees zero rows.
    sql = _filtered("external_writes", principal="alice").lower()
    assert "false" in sql or "0 = 1" in sql


def test_filter_workspace_id_scopes_when_column_present() -> None:
    sql = _filtered("ops", workspace_id=42)
    assert "workspace_id = 42" in sql
