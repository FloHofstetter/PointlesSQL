"""Anomaly detection over the cockpit time series.

For each bin in the requested window, computes a rolling
mean/stddev over the prior ``window_days`` (excluding the bin
itself) and flags ``ok`` / ``warn`` / ``critical`` per
:func:`_classify`.  Used by both the cockpit anomaly chart and
the per-run anomaly verdict that lands on
``agent_runs.anomaly_severity``.
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.enums import RunStatus
from pointlessql.models import AgentRun
from pointlessql.services.audit_aggregator._query_builder import (
    Bin,
    Metric,
    Severity,
)
from pointlessql.services.audit_aggregator._timeseries import timeseries

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


RUN_ANOMALY_METRICS: tuple[Metric, ...] = ("rejects", "errored_ops")
"""Metrics evaluated per-run for the inbox + run-list-badge.

The cache (``agent_runs.anomaly_severity`` + ``anomaly_metric``)
only persists the worst breach across these two — the same signals
the run-detail anomaly chip uses.  Expanding this tuple later just
requires a backfill, not a schema change.
"""

_SEVERITY_RANK: dict[str, int] = {"ok": 0, "warn": 1, "critical": 2}


def _classify(observed: float, mean: float, std: float, sigma_threshold: float) -> Severity:
    """Map an observation onto an :data:`Severity` level.

    "Critical" requires both the absolute spike (``observed > mean +
    2σ``) AND the configured sigma multiple — so a single noisy
    point on a low-variance series doesn't keep paging on-call once
    operators raise the threshold.

    Args:
        observed: The observed value at the current bin.
        mean: Rolling-baseline mean.
        std: Rolling-baseline standard deviation.
        sigma_threshold: σ-multiplier — ``warn`` ≥ this above mean,
            ``critical`` ≥ ``2 ×`` this.

    Returns:
        ``"ok"`` / ``"warn"`` / ``"critical"``.
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


def _bin_floor_compare_string(since: datetime.datetime, bin_: Bin) -> str:
    """Return a bin-precision prefix string for lexicographic compare.

    ``timeseries`` emits bin strings shaped by :func:`bin_expr`:
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
            .where(AgentRun.status.in_((RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.DENIED)))
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
