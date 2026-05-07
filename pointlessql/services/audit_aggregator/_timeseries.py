"""Time-binned metric series, optionally grouped by table or principal.

Drives the cockpit's Chart.js line/stacked-bar surfaces.  Each
point carries ``ts`` (bin string), optional ``group`` (table FQN /
principal), and the aggregated ``value``.  Points are ordered
``ts ASC`` so the chart x-axis stays monotonic.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import AgentRun
from pointlessql.services.audit_aggregator._query_builder import (
    VALID_BINS,
    VALID_GROUP_BY,
    VALID_METRICS,
    Bin,
    GroupBy,
    Metric,
    MetricSpec,
    apply_audit_filters,
    bin_expr,
    metric_spec,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _group_col(spec: MetricSpec, group_by: GroupBy) -> Any:
    """Pick the GROUP BY column (or ``None`` for ``"none"``).

    For ``table`` grouping we use ``spec.target_col`` directly when
    available; for ``principal`` grouping we always project
    :attr:`AgentRun.principal`, which means the caller's join on
    ``AgentRun`` (added by :func:`apply_audit_filters` when needed)
    must already be in scope.

    Args:
        spec: Active metric specification.
        group_by: Caller's grouping choice.

    Returns:
        The column expression, or ``None`` for the un-grouped case.
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

    spec = metric_spec(metric)  # type: ignore[arg-type]
    points: list[dict[str, Any]] = []
    with factory() as session:
        bin_col = bin_expr(
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
            stmt = stmt.group_by(bin_col).order_by(bin_col)
            for ts, value in session.execute(stmt).all():
                points.append({"ts": ts, "value": int(value or 0)})
        else:
            stmt = select(
                bin_col.label("ts"),
                group_col.label("group"),
                spec.measure.label("value"),
            )
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
