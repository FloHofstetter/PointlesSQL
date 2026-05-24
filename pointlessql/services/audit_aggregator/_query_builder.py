"""Shared SQL aggregation foundation for the cockpit.

Type aliases (``Metric`` / ``Bin`` / ``GroupBy`` / ``Severity``),
the ``MetricSpec`` dataclass, and the column-/filter-/scalar-
aggregation helpers every public surface (summary / timeseries /
anomaly) imports.  Splitting these out keeps the ~150 LOC
``metric_spec`` switch in one place; the surfaces never duplicate
table or filter logic.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import (
    String,
    and_,
    cast,
    func,
    literal,
    select,
)

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunToolCall,
    LineageRowReject,
    LineageValueChange,
    QueryHistory,
    UnattributedWrite,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select


Metric = Literal[
    "runs",
    "ops",
    "errored_ops",
    "rows_written",
    "value_changes",
    "rejects",
    "expectation_failures",
    "external_writes",
    "cost_denials",
    "tool_calls",
    "queries",
]

Bin = Literal["hour", "day", "week"]
GroupBy = Literal["none", "table", "principal"]
Severity = Literal["ok", "warn", "critical"]

VALID_METRICS: frozenset[str] = frozenset(
    {
        "runs",
        "ops",
        "errored_ops",
        "rows_written",
        "value_changes",
        "rejects",
        "expectation_failures",
        "external_writes",
        "cost_denials",
        "tool_calls",
        "queries",
    }
)
VALID_BINS: frozenset[str] = frozenset({"hour", "day", "week"})
VALID_GROUP_BY: frozenset[str] = frozenset({"none", "table", "principal"})


@dataclass(frozen=True)
class MetricSpec:
    """Static description of how to query one cockpit metric.

    Encapsulates "which table, which timestamp column, which row
    counts" so the three public surfaces stay short and the SQL
    lives in one table-of-truth instead of being duplicated three
    ways.

    Column-shaped fields use ``Any`` rather than
    :class:`ColumnElement` so SQLAlchemy's
    :class:`InstrumentedAttribute` mapped columns drop in cleanly
    — the type alias is structural for our SQL builder.
    """

    table: type
    timestamp_col: Any
    target_col: Any
    run_id_col: Any
    where: Any
    measure: Any
    requires_run_join: bool


def metric_spec(metric: Metric) -> MetricSpec:
    """Return the :class:`MetricSpec` for a cockpit metric.

    Centralised so :func:`summary`, :func:`timeseries`, and
    :func:`anomalies` all share the same columns + filter logic.

    Args:
        metric: One of :data:`VALID_METRICS`.

    Returns:
        The :class:`MetricSpec` for that metric.
    """
    if metric == "runs":
        return MetricSpec(
            table=AgentRun,
            timestamp_col=AgentRun.started_at,
            target_col=None,
            run_id_col=AgentRun.id,
            where=None,
            measure=func.count(AgentRun.id),
            requires_run_join=False,
        )
    if metric == "ops":
        return MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=None,
            measure=func.count(AgentRunOperation.id),
            requires_run_join=False,
        )
    if metric == "errored_ops":
        return MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=AgentRunOperation.error_message.is_not(None),
            measure=func.count(AgentRunOperation.id),
            requires_run_join=False,
        )
    if metric == "rows_written":
        return MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=AgentRunOperation.op_name.in_(("merge", "write_table")),
            measure=func.coalesce(func.sum(AgentRunOperation.rows_affected), 0),
            requires_run_join=False,
        )
    if metric == "value_changes":
        return MetricSpec(
            table=LineageValueChange,
            timestamp_col=LineageValueChange.created_at,
            target_col=LineageValueChange.target_table,
            run_id_col=LineageValueChange.run_id,
            where=None,
            measure=func.count(LineageValueChange.id),
            requires_run_join=False,
        )
    if metric == "rejects":
        return MetricSpec(
            table=LineageRowReject,
            timestamp_col=LineageRowReject.created_at,
            target_col=LineageRowReject.source_table,
            run_id_col=LineageRowReject.run_id,
            where=None,
            measure=func.count(LineageRowReject.id),
            requires_run_join=False,
        )
    if metric == "expectation_failures":
        # rejects with reason ``expectation_failed`` are
        # the dbt-bridge's per-test-failure markers.  Same table as
        # ``rejects`` with a row-level filter so the cockpit can show
        # dbt-side data-quality failures separately from merge-time
        # rejects (which carry the engine-level ``on_key_null`` etc.).
        return MetricSpec(
            table=LineageRowReject,
            timestamp_col=LineageRowReject.created_at,
            target_col=LineageRowReject.source_table,
            run_id_col=LineageRowReject.run_id,
            where=LineageRowReject.reason == "expectation_failed",
            measure=func.count(LineageRowReject.id),
            requires_run_join=False,
        )
    if metric == "external_writes":
        return MetricSpec(
            table=UnattributedWrite,
            timestamp_col=UnattributedWrite.detected_at,
            target_col=UnattributedWrite.table_fqn,
            run_id_col=None,
            where=None,
            measure=func.count(UnattributedWrite.id),
            requires_run_join=False,
        )
    if metric == "cost_denials":
        return MetricSpec(
            table=AgentRun,
            timestamp_col=AgentRun.started_at,
            target_col=None,
            run_id_col=AgentRun.id,
            where=and_(
                AgentRun.status == "denied",
                AgentRun.cost_gate_trigger.is_not(None),
            ),
            measure=func.count(AgentRun.id),
            requires_run_join=False,
        )
    if metric == "tool_calls":
        return MetricSpec(
            table=AgentRunToolCall,
            timestamp_col=AgentRunToolCall.called_at,
            target_col=None,
            run_id_col=AgentRunToolCall.agent_run_id,
            where=None,
            measure=func.count(AgentRunToolCall.id),
            requires_run_join=False,
        )
    # ``queries`` — table-FQN filter is intentionally ignored here:
    # ``query_history.sql_text`` is opaque, and the cross-axis
    # filter at the row level lives on :class:`QueryHistoryTable`.
    # For audit-summary purposes the unfiltered count is what the
    # personas need.
    return MetricSpec(
        table=QueryHistory,
        timestamp_col=QueryHistory.started_at,
        target_col=None,
        run_id_col=QueryHistory.agent_run_id,
        where=None,
        measure=func.count(QueryHistory.id),
        requires_run_join=False,
    )


def bin_expr(
    timestamp_col: Any,
    bin_: Bin,
    dialect_name: str,
) -> Any:
    """Return a dialect-correct expression that buckets ``timestamp_col``.

    SQLite uses ``strftime`` for hour + week (no ``date_trunc``) and
    ``date()`` for day; Postgres uses ``date_trunc`` everywhere.

    The output is always a scalar string so the GROUP BY + ORDER BY
    semantics are consistent regardless of dialect — Postgres
    callers can re-cast to timestamp on the client if needed.

    Args:
        timestamp_col: SQLAlchemy column expression to bucket.
        bin_: ``"hour"`` / ``"day"`` / ``"week"``.
        dialect_name: Result of ``engine.dialect.name`` — typically
            ``"sqlite"`` or ``"postgresql"``.

    Returns:
        A scalar string column expression that can drive both a
        GROUP BY and a SELECT.
    """
    is_postgres = dialect_name.startswith("postgres")
    if bin_ == "hour":
        if is_postgres:
            return cast(func.date_trunc("hour", timestamp_col), String)
        return func.strftime("%Y-%m-%d %H:00", timestamp_col)
    if bin_ == "day":
        if is_postgres:
            return cast(func.date_trunc("day", timestamp_col), String)
        return func.strftime("%Y-%m-%d", timestamp_col)
    # week — Sunday-anchored to mirror the Grafana 7-day baseline.
    if is_postgres:
        return cast(func.date_trunc("week", timestamp_col), String)
    return func.strftime("%Y-%W", timestamp_col)


def apply_audit_filters(
    stmt: Select[Any],
    spec: MetricSpec,
    *,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    principal: str | None,
    agent_id: str | None,
    table: str | None,
    workspace_id: int | None = None,
) -> Select[Any]:
    """Apply the cockpit's standard filter set to a SELECT.

    All filters are AND-ed.  ``principal`` and ``agent_id`` join to
    :class:`AgentRun` when the metric's primary table doesn't carry
    those columns; for metrics with no run linkage (``external_writes``)
    the filters return zero rows when set, by design.

    Args:
        stmt: The base SELECT to extend.
        spec: Metric specification driving column selection.
        since: Lower bound (inclusive) on the metric's timestamp
            column.
        until: Upper bound (exclusive) on the metric's timestamp
            column.
        principal: Filter to runs whose principal matches.
        agent_id: Filter to runs whose agent_id matches.
        table: Filter to rows whose target table matches.  Maps to
            ``target_table`` for ops/lineage and ``table_fqn`` for
            external writes; ignored for run-level metrics.
        workspace_id: Workspace lens.  ``None`` opts into
            the cross-workspace view (tenant admin only); a concrete id
            restricts results to that workspace.

    Returns:
        The extended SELECT statement.
    """
    if since is not None:
        stmt = stmt.where(spec.timestamp_col >= since)
    if until is not None:
        stmt = stmt.where(spec.timestamp_col < until)
    if spec.where is not None:
        stmt = stmt.where(spec.where)
    # Workspace lens.  Every metric's primary table carries a NOT
    # NULL workspace_id column, so the filter applies uniformly via
    # ``getattr``.  ``None`` means the caller (a tenant admin via
    # ?workspace=all) opted into the cross-workspace lens.
    if workspace_id is not None:
        ws_col = getattr(spec.table, "workspace_id", None)
        if ws_col is not None:
            stmt = stmt.where(ws_col == workspace_id)
    if table is not None and table.strip() and spec.target_col is not None:
        stmt = stmt.where(spec.target_col == table.strip())
    elif table is not None and table.strip() and spec.target_col is None:
        # Run-level metric: filter via tables_touched JSON contains.
        # Cheap LIKE — the column is JSON text, the table_fqn is
        # bracketed by quotes so substring matching is safe.
        stmt = stmt.where(
            AgentRun.tables_touched.ilike(f'%"{table.strip()}"%')
            if spec.table is AgentRun
            else literal(False)
        )
    needs_run_join = principal is not None or agent_id is not None
    if needs_run_join and spec.run_id_col is None:
        # External writes have no run linkage; filter out everything
        # so the caller sees a clean empty result.
        return stmt.where(literal(False))
    if needs_run_join and spec.table is not AgentRun:
        stmt = stmt.join(AgentRun, AgentRun.id == spec.run_id_col)
    if principal is not None and principal.strip():
        stmt = stmt.where(AgentRun.principal == principal.strip())
    if agent_id is not None and agent_id.strip():
        stmt = stmt.where(AgentRun.agent_id == agent_id.strip())
    return stmt


def scalar_count(
    session: Session,
    metric: Metric,
    *,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    principal: str | None,
    agent_id: str | None,
    table: str | None,
    workspace_id: int | None = None,
) -> int:
    """Execute a single-row aggregation and return the integer value.

    Used by :func:`summary` for every metric; null-coalesced to ``0``
    so a no-rows window never returns ``None`` to the API surface.

    Args:
        session: Open SQLAlchemy session.
        metric: Cockpit metric to count.
        since: Lower bound (inclusive) on the metric's timestamp.
        until: Upper bound (exclusive) on the metric's timestamp.
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Target-table filter.
        workspace_id: Workspace lens.  ``None`` means cross-workspace
            (admin-only super-admin lens); an int scopes to that
            workspace.

    Returns:
        The integer count, or ``0`` for empty windows.
    """
    spec = metric_spec(metric)
    stmt = select(spec.measure)
    stmt = apply_audit_filters(
        stmt,
        spec,
        since=since,
        until=until,
        principal=principal,
        agent_id=agent_id,
        table=table,
        workspace_id=workspace_id,
    )
    raw = session.execute(stmt).scalar()
    return int(raw or 0)
