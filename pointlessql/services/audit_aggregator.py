"""SQL aggregation backbone for the  Audit Cockpit.

Three pure-SQL aggregations compose every cockpit surface:

* :func:`summary` — single-dict counts for the four "is anything
  exploding right now?" personas.
* :func:`timeseries` — point-list binned over time, optionally
  grouped by ``table`` or ``principal``.
* :func:`anomalies` — same shape as ``timeseries`` plus a
  ``baseline_mean``/``baseline_std``/``sigma``/``severity`` per
  point computed against an N-day rolling window.

All three share a single filter helper so a future
``/api/audit/<surface>`` route can re-use the same WHERE clause.
The filter helper is timestamp-column-aware: each metric points at
its own ``timestamp_col`` (``started_at`` for runs/ops,
``created_at`` for lineage tables, ``detected_at`` for
``unattributed_writes``, ``called_at`` for tool calls).

No new persistence — the service queries the existing tables
directly.  The roadmap revisit threshold for materialising results
is >100M datapoints/year *or* >2s p95 on
``/api/audit/anomalies``.
"""

from __future__ import annotations

import datetime
import logging
import math
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
    from sqlalchemy.orm import Session, sessionmaker
    from sqlalchemy.sql import Select

logger = logging.getLogger(__name__)


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
class _MetricSpec:
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


def _metric_spec(metric: Metric) -> _MetricSpec:
    """Return the :class:`_MetricSpec` for a cockpit metric.

    Centralised so :func:`summary`, :func:`timeseries`, and
    :func:`anomalies` all share the same columns + filter logic.
    """
    if metric == "runs":
        return _MetricSpec(
            table=AgentRun,
            timestamp_col=AgentRun.started_at,
            target_col=None,
            run_id_col=AgentRun.id,
            where=None,
            measure=func.count(AgentRun.id),
            requires_run_join=False,
        )
    if metric == "ops":
        return _MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=None,
            measure=func.count(AgentRunOperation.id),
            requires_run_join=False,
        )
    if metric == "errored_ops":
        return _MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=AgentRunOperation.error_message.is_not(None),
            measure=func.count(AgentRunOperation.id),
            requires_run_join=False,
        )
    if metric == "rows_written":
        return _MetricSpec(
            table=AgentRunOperation,
            timestamp_col=AgentRunOperation.started_at,
            target_col=AgentRunOperation.target_table,
            run_id_col=AgentRunOperation.agent_run_id,
            where=AgentRunOperation.op_name.in_(("merge", "write_table")),
            measure=func.coalesce(func.sum(AgentRunOperation.rows_affected), 0),
            requires_run_join=False,
        )
    if metric == "value_changes":
        return _MetricSpec(
            table=LineageValueChange,
            timestamp_col=LineageValueChange.created_at,
            target_col=LineageValueChange.target_table,
            run_id_col=LineageValueChange.run_id,
            where=None,
            measure=func.count(LineageValueChange.id),
            requires_run_join=False,
        )
    if metric == "rejects":
        return _MetricSpec(
            table=LineageRowReject,
            timestamp_col=LineageRowReject.created_at,
            target_col=LineageRowReject.source_table,
            run_id_col=LineageRowReject.run_id,
            where=None,
            measure=func.count(LineageRowReject.id),
            requires_run_join=False,
        )
    if metric == "expectation_failures":
        # Sprint 36.3 — rejects with reason ``expectation_failed`` are
        # the dbt-bridge's per-test-failure markers.  Same table as
        # ``rejects`` with a row-level filter so the cockpit can show
        # dbt-side data-quality failures separately from merge-time
        # rejects (which carry the engine-level ``on_key_null`` etc.).
        return _MetricSpec(
            table=LineageRowReject,
            timestamp_col=LineageRowReject.created_at,
            target_col=LineageRowReject.source_table,
            run_id_col=LineageRowReject.run_id,
            where=LineageRowReject.reason == "expectation_failed",
            measure=func.count(LineageRowReject.id),
            requires_run_join=False,
        )
    if metric == "external_writes":
        return _MetricSpec(
            table=UnattributedWrite,
            timestamp_col=UnattributedWrite.detected_at,
            target_col=UnattributedWrite.table_fqn,
            run_id_col=None,
            where=None,
            measure=func.count(UnattributedWrite.id),
            requires_run_join=False,
        )
    if metric == "cost_denials":
        return _MetricSpec(
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
        return _MetricSpec(
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
    return _MetricSpec(
        table=QueryHistory,
        timestamp_col=QueryHistory.started_at,
        target_col=None,
        run_id_col=QueryHistory.agent_run_id,
        where=None,
        measure=func.count(QueryHistory.id),
        requires_run_join=False,
    )


def _bin_expr(
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


def _apply_audit_filters(
    stmt: Select[Any],
    spec: _MetricSpec,
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


def _scalar_count(
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
    spec = _metric_spec(metric)
    stmt = select(spec.measure)
    stmt = _apply_audit_filters(
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


def summary(
    factory: sessionmaker[Session],
    *,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    principal: str | None = None,
    agent_id: str | None = None,
    table: str | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    """Return a single-dict cockpit summary across every metric.

    The shape is deliberately flat — the cockpit UI renders it as
    stat-cards with no further parsing.  When every filter is
    ``None`` the response covers the full retention window, matching
    "since the beginning of recorded time" semantics.

    Args:
        factory: SQLAlchemy session factory.
        since: Lower bound (inclusive) on each metric's timestamp.
        until: Upper bound (exclusive) on each metric's timestamp.
        principal: ``AgentRun.principal`` filter applied where
            possible (run-attached metrics).
        agent_id: ``AgentRun.agent_id`` filter applied where
            possible.
        table: Target-table filter applied to op/lineage metrics
            (``target_table``) and external writes (``table_fqn``).
        workspace_id: Workspace lens.  ``None`` opts into
            the cross-workspace view (tenant admin only); a concrete id
            restricts results to that workspace.

    Returns:
        Dict with one key per metric in :data:`VALID_METRICS`.
    """
    with factory() as session:
        return {
            metric: _scalar_count(
                session,
                metric,  # type: ignore[arg-type]
                since=since,
                until=until,
                principal=principal,
                agent_id=agent_id,
                table=table,
                workspace_id=workspace_id,
            )
            for metric in sorted(VALID_METRICS)
        }


def _group_col(spec: _MetricSpec, group_by: GroupBy) -> Any:
    """Pick the GROUP BY column (or ``None`` for ``"none"``).

    For ``table`` grouping we use ``spec.target_col`` directly when
    available; for ``principal`` grouping we always project
    :attr:`AgentRun.principal`, which means the caller's join on
    ``AgentRun`` (added by :func:`_apply_audit_filters` when needed)
    must already be in scope.
    """
    if group_by == "none":
        return None
    if group_by == "table":
        return spec.target_col
    if group_by == "principal":
        return AgentRun.principal
    return None


def timeseries(
    factory: sessionmaker[Session],
    *,
    metric: Metric,
    bin_: Bin = "day",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    principal: str | None = None,
    agent_id: str | None = None,
    table: str | None = None,
    group_by: GroupBy = "none",
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Return a time-binned series of one metric, optionally grouped.

    The resulting dict is shaped for direct rendering into Chart.js
    line/stacked-bar series: each point carries a ``ts`` (the bin
    string), an optional ``group`` (table FQN / principal), and the
    aggregated ``value``.  Points are ordered ``ts ASC`` to keep the
    chart x-axis monotonic.

    Args:
        factory: SQLAlchemy session factory.
        metric: One of :data:`VALID_METRICS`.
        bin_: ``"hour"`` / ``"day"`` / ``"week"``.
        since: Lower bound (inclusive) on the metric's timestamp.
        until: Upper bound (exclusive) on the metric's timestamp.
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Target-table filter.
        group_by: ``"none"`` returns one series; ``"table"`` /
            ``"principal"`` produce one series per group.  When the
            metric has no group column (e.g. ``cost_denials`` +
            ``table``) the series collapses to ``"none"``.
        workspace_id: Workspace lens.  ``None`` opts into
            the cross-workspace view (tenant admin only); a concrete id
            restricts results to that workspace.

    Returns:
        ``{"metric", "bin", "group_by", "points": [...]}``.

    Raises:
        ValueError: ``metric``/``bin_``/``group_by`` are outside
            their respective whitelists.
    """
    if metric not in VALID_METRICS:
        raise ValueError(f"unknown metric: {metric!r}")
    if bin_ not in VALID_BINS:
        raise ValueError(f"unknown bin: {bin_!r}")
    if group_by not in VALID_GROUP_BY:
        raise ValueError(f"unknown group_by: {group_by!r}")

    spec = _metric_spec(metric)  # type: ignore[arg-type]
    points: list[dict[str, Any]] = []
    with factory() as session:
        bin_col = _bin_expr(
            spec.timestamp_col, bin_, session.bind.dialect.name if session.bind else "sqlite"
        )
        group_col = _group_col(spec, group_by)
        # Falling back to ``"none"`` quietly when the metric doesn't
        # support the requested grouping keeps callers' UI code
        # branchless.
        if group_by != "none" and group_col is None:
            group_by = "none"

        if group_col is None:
            stmt = select(bin_col.label("ts"), spec.measure.label("value"))
            stmt = _apply_audit_filters(
                stmt,
                spec,
                since=since,
                until=until,
                principal=principal,
                agent_id=agent_id,
                table=table,
                workspace_id=workspace_id,
            )
            stmt = stmt.group_by(bin_col).order_by(bin_col)
            for ts, value in session.execute(stmt).all():
                points.append({"ts": ts, "value": int(value or 0)})
        else:
            stmt = select(
                bin_col.label("ts"),
                group_col.label("group"),
                spec.measure.label("value"),
            )
            stmt = _apply_audit_filters(
                stmt,
                spec,
                since=since,
                until=until,
                principal=principal,
                agent_id=agent_id,
                table=table,
                workspace_id=workspace_id,
            )
            stmt = stmt.group_by(bin_col, group_col).order_by(bin_col, group_col)
            for ts, grp, value in session.execute(stmt).all():
                points.append(
                    {
                        "ts": ts,
                        "group": grp,
                        "value": int(value or 0),
                    }
                )
    return {
        "metric": metric,
        "bin": bin_,
        "group_by": group_by,
        "points": points,
    }


def _classify(observed: float, mean: float, std: float, sigma_threshold: float) -> Severity:
    """Map an observation onto an :data:`Severity` level.

    "Critical" requires both the absolute spike (``observed > mean +
    2σ``) AND the configured sigma multiple — so a single noisy
    point on a low-variance series doesn't keep paging on-call once
    operators raise the threshold.
    """
    if std <= 0.0:
        # Zero-variance baseline: anything non-zero above mean is at
        # least a warn; zeros and dips are ok.
        if observed > mean and mean == 0:
            return "critical" if observed > 0 else "ok"
        if observed > mean:
            return "warn"
        return "ok"
    distance_sigma = (observed - mean) / std
    if distance_sigma >= sigma_threshold * 2:
        return "critical"
    if distance_sigma >= sigma_threshold:
        return "warn"
    return "ok"


def anomalies(
    factory: sessionmaker[Session],
    *,
    metric: Metric,
    window_days: int = 7,
    sigma: float = 2.0,
    bin_: Bin = "day",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    principal: str | None = None,
    agent_id: str | None = None,
    table: str | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Return one anomaly verdict per bin in the requested window.

    For each ``ts`` in the observed series, computes the rolling
    mean + stddev over the previous ``window_days`` (excluding the
    point itself) and flags it ``ok`` / ``warn`` / ``critical`` per
    :func:`_classify`.

    The math runs in Python rather than as a window function so the
    same code path works on SQLite (no native window support for
    standard deviation in older versions) and Postgres.  The query
    cap is the timeseries result size, which the caller controls
    via ``since``/``until``; without bounds the function reads the
    full retention window.

    Args:
        factory: SQLAlchemy session factory.
        metric: One of :data:`VALID_METRICS`.
        window_days: Rolling-window size in days.  Must be >= 1.
        sigma: Threshold multiplier; ``warn`` ≥ this many σ above
            the baseline, ``critical`` ≥ ``2 × this``.
        bin_: ``"hour"`` / ``"day"`` / ``"week"``.
        since: Lower bound (inclusive) on the metric's timestamp.
        until: Upper bound (exclusive) on the metric's timestamp.
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Target-table filter.
        workspace_id: Workspace lens.  ``None`` opts into
            the cross-workspace view (tenant admin only); a concrete id
            restricts results to that workspace.

    Returns:
        ``{"metric", "baseline_window_days", "threshold_sigma",
        "bin", "points": [{"ts", "observed", "baseline_mean",
        "baseline_std", "sigma", "severity"}]}``.

    Raises:
        ValueError: ``window_days`` is < 1, or :func:`timeseries`
            rejects the ``metric``/``bin_`` enum.
    """
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    #  baseline-coverage fix: when the caller bounds
    # ``since`` to (e.g.) yesterday, the previous behaviour returned
    # only points inside ``[since, until)`` to the rolling-baseline
    # loop, which meant the first bin in the window had an empty
    # baseline and therefore every point looked anomalous.  Widen
    # the underlying timeseries query by ``window_days`` so the
    # rolling baseline always has prior context, then trim the
    # response back to ``[since, until)`` for the caller.
    extended_since: datetime.datetime | None = None
    if since is not None:
        extended_since = since - datetime.timedelta(days=window_days)
    series = timeseries(
        factory,
        metric=metric,
        bin_=bin_,
        since=extended_since,
        until=until,
        principal=principal,
        agent_id=agent_id,
        table=table,
        group_by="none",
        workspace_id=workspace_id,
    )
    raw_points = series["points"]
    out: list[dict[str, Any]] = []
    if bin_ == "hour":
        window_size = max(1, window_days * 24)
    elif bin_ == "week":
        window_size = max(1, window_days // 7 or 1)
    else:
        window_size = max(1, window_days)
    since_floor = _bin_floor_compare_string(since, bin_) if since is not None else None
    for i, point in enumerate(raw_points):
        baseline_slice = raw_points[max(0, i - window_size) : i]
        baseline_values = [float(p["value"]) for p in baseline_slice]
        if baseline_values:
            mean = sum(baseline_values) / len(baseline_values)
            variance = sum((v - mean) ** 2 for v in baseline_values) / len(baseline_values)
            std = math.sqrt(variance)
        else:
            mean = 0.0
            std = 0.0
        observed = float(point["value"])
        sigma_distance = (observed - mean) / std if std > 0 else 0.0
        # Trim points that pre-date the caller's ``since`` — they
        # only exist in the result to seed the rolling baseline.
        # Compare bin-precision prefixes so SQLite ("2026-04-27")
        # and Postgres ("2026-04-27 00:00:00+00") agree.
        if since_floor:
            ts_prefix = str(point["ts"])[: len(since_floor)]
            if ts_prefix < since_floor:
                continue
        out.append(
            {
                "ts": point["ts"],
                "observed": int(observed),
                "baseline_mean": round(mean, 4),
                "baseline_std": round(std, 4),
                "sigma": round(sigma_distance, 4),
                "severity": _classify(observed, mean, std, sigma),
            }
        )
    return {
        "metric": metric,
        "baseline_window_days": window_days,
        "threshold_sigma": sigma,
        "bin": bin_,
        "points": out,
    }


RUN_ANOMALY_METRICS: tuple[Metric, ...] = ("rejects", "errored_ops")
"""Metrics evaluated per-run for the inbox + run-list-badge.

The cache (``agent_runs.anomaly_severity`` + ``anomaly_metric``)
only persists the worst breach across these two — the same signals
the run-detail anomaly chip uses.  Expanding this tuple later just
requires a backfill, not a schema change.
"""

_SEVERITY_RANK: dict[str, int] = {"ok": 0, "warn": 1, "critical": 2}


def compute_run_anomaly(
    factory: sessionmaker[Session],
    run_row: AgentRun,
    *,
    window_days: int = 7,
    sigma: float = 2.0,
) -> dict[str, Any] | None:
    """Return the worst day-bin anomaly verdict for a run, or ``None``.

    Anchors the verdict on the run's ``started_at`` day-bin and
    asks :func:`anomalies` for that single bin (with ``window_days``
    of prior baseline context).  Iterates :data:`RUN_ANOMALY_METRICS`
    and keeps the highest severity.  Used by both the run-finish
    hook (which writes the result back into ``agent_runs``) and the
    run-detail chip (which re-renders the live observation alongside
    the persisted severity).

    Best-effort: any failure logs and returns ``None`` so a broken
    aggregator never blocks the calling code path.

    Args:
        factory: SQLAlchemy session factory.
        run_row: The :class:`AgentRun` ORM row to evaluate.  Must
            carry a non-``None`` ``started_at`` — runs without a
            start timestamp return ``None`` directly.
        window_days: Rolling-window size in days for the baseline.
        sigma: σ-multiplier — ``warn`` ≥ this above mean,
            ``critical`` ≥ ``2 ×`` this.

    Returns:
        ``{"metric", "severity", "observed", "baseline_mean",
        "sigma"}`` for the worst breach, or ``None`` when no metric
        breaches the threshold (or anything failed).
    """
    try:
        anchor: datetime.datetime | None = getattr(run_row, "started_at", None)
        if anchor is None:
            return None
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=datetime.UTC)
        day_start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + datetime.timedelta(days=1)
        worst: dict[str, Any] | None = None
        for metric in RUN_ANOMALY_METRICS:
            result = anomalies(
                factory,
                metric=metric,
                window_days=window_days,
                sigma=sigma,
                bin_="day",
                since=day_start,
                until=day_end,
            )
            points = result["points"]
            if not points:
                continue
            point = points[0]
            if point["severity"] == "ok":
                continue
            if worst is None or _SEVERITY_RANK[point["severity"]] > _SEVERITY_RANK.get(
                worst["severity"], 0
            ):
                worst = {
                    "metric": metric,
                    "severity": point["severity"],
                    "observed": point["observed"],
                    "baseline_mean": point["baseline_mean"],
                    "sigma": point["sigma"],
                }
        return worst
    except Exception:  # noqa: BLE001 — verdict is best-effort
        logger.exception("compute_run_anomaly failed for run %s", getattr(run_row, "id", "?"))
        return None


def backfill_run_anomalies(
    factory: sessionmaker[Session],
    *,
    window_days: int = 7,
    sigma: float = 2.0,
    limit: int | None = None,
) -> int:
    """Recompute and persist anomaly verdicts on terminal runs.

    Walks every :class:`AgentRun` in a terminal status whose
    ``anomaly_severity`` column is still ``NULL``, calls
    :func:`compute_run_anomaly`, and writes the result back.  Used
    once after the anomaly-cache alembic migration to populate
    badges for historical runs without coupling the migration
    itself to the service layer.

    Args:
        factory: SQLAlchemy session factory.
        window_days: Rolling-window size in days for the baseline.
        sigma: σ-multiplier for the warn / critical split.
        limit: Optional cap on how many runs to process per call —
            useful for chunked operator-driven backfills on huge
            audit lakes.  ``None`` processes every NULL row in one
            session.

    Returns:
        The number of runs that received a non-``NULL`` verdict.
    """
    written = 0
    with factory() as session:
        stmt = (
            select(AgentRun)
            .where(AgentRun.status.in_(("succeeded", "failed", "denied")))
            .where(AgentRun.anomaly_severity.is_(None))
            .order_by(AgentRun.started_at)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(session.scalars(stmt).all())
        for row in rows:
            verdict = compute_run_anomaly(factory, row, window_days=window_days, sigma=sigma)
            if verdict is None:
                continue
            row.anomaly_severity = verdict["severity"]
            row.anomaly_metric = verdict["metric"]
            written += 1
        session.commit()
    return written


def _bin_floor_compare_string(since: datetime.datetime, bin_: Bin) -> str:
    """Return a bin-precision prefix string for lexicographic compare.

    ``timeseries`` emits bin strings shaped by :func:`_bin_expr`:
    SQLite gives ``%Y-%m-%d`` / ``%Y-%m-%d %H:00`` / ``%Y-%W``;
    Postgres casts a ``date_trunc`` result to a string that starts
    with the same date/hour prefix but carries seconds + offset
    suffixes.  Comparing both against a bin-precision prefix of
    *since* keeps the trim correct on either dialect.  Returned
    strings have lengths 10 (day), 16 (hour), or 7 (week) — the
    caller slices the point's ``ts`` to that length before the
    compare.

    Args:
        since: Caller-supplied lower bound.
        bin_: Active bin width.

    Returns:
        Prefix string suitable for ``ts[:len(prefix)] < prefix``
        compares.
    """
    if bin_ == "day":
        return since.strftime("%Y-%m-%d")
    if bin_ == "hour":
        return since.strftime("%Y-%m-%d %H:00")
    # week: SQLite uses ISO week index (``%Y-%W``); Postgres uses
    # the Monday date_trunc form which begins with the date of that
    # Monday — the two formats diverge so we fall back to keeping
    # the seed weeks in the response.  Week-bin anomaly detection
    # is rare in practice (cron uses day) and the small inflation
    # is documented in the docstring.
    return ""
