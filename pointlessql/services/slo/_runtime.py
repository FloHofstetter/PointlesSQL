"""Runtime-measurement implementations for the 4 decl-only SLO kinds.

Consolidates ``timeliness`` / ``precision_accuracy`` / ``availability``
/ ``performance`` measurers behind one dispatch helper that the
workspace scan calls.  Each measurer returns
``(verdict, detail_dict)`` so the audit + drill-down surface is
identical to the existing measurable kinds.

Substrate the measurers read:

* timeliness         ← event-time vs processing-time on bitemporal
  columns declared in the product's bitemporal policy.
* precision_accuracy ← null-ratio on declared error columns from the
  most-recent ``DataProductStatistics`` snapshot.
* availability       ← ``data_product_availability_probes`` rolling
  7-day window.
* performance        ← ``data_product_query_perf_samples`` rolling
  N-sample p95.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import (
    DataProductAvailabilityProbe,
    DataProductQueryPerfSample,
    DataProductStatistics,
)
from pointlessql.types import SessionFactory


def _percentile_sorted(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * q
    lo = int(rank)
    hi = min(lo + 1, len(values) - 1)
    frac = rank - lo
    return float(values[lo] * (1 - frac) + values[hi] * frac)


def measure_timeliness(
    factory: SessionFactory,
    *,
    data_product_id: int,
    event_time_col: str | None,
    processing_time_col: str | None,
    target_value: float,
    comparator: str = "lte",
) -> tuple[str, dict[str, Any]]:
    """Compute timeliness p95 from bitemporal columns.

    Without a declared bitemporal policy returns ``unmeasured``.  When
    both columns are declared we cannot read the underlying Delta
    table without an engine, so the substrate-only verdict reflects
    *declaration completeness* — a sentinel value the UI surfaces as
    "policy declared, measurement engine not yet wired".

    The full table-scan path is the responsibility of a later
    iteration; this function keeps the dispatcher API stable.
    """
    if not event_time_col or not processing_time_col:
        return "unmeasured", {
            "reason": "bitemporal policy required",
        }
    return "unmeasured", {
        "reason": "engine-side measurement not wired in this revision",
        "event_time_col": event_time_col,
        "processing_time_col": processing_time_col,
        "target_value": target_value,
        "comparator": comparator,
    }


def measure_precision_accuracy(
    factory: SessionFactory,
    *,
    data_product_id: int,
    table_name: str | None,
    target_value: float,
    comparator: str = "lte",
) -> tuple[str, dict[str, Any]]:
    """Compute the null/error ratio from the latest statistics snapshot."""
    with factory() as session:
        stmt = (
            select(DataProductStatistics)
            .where(DataProductStatistics.data_product_id == data_product_id)
            .order_by(DataProductStatistics.created_at.desc())
            .limit(1)
        )
        if table_name:
            stmt = stmt.where(DataProductStatistics.table_name == table_name)
        snapshot = session.scalar(stmt)
    if snapshot is None:
        return "unmeasured", {"reason": "no statistics snapshot"}
    try:
        payload = json.loads(snapshot.shape_json or "{}")
    except (ValueError, TypeError):
        payload = {}
    null_ratio = float(payload.get("null_ratio_max", 0.0) or 0.0)
    if comparator == "lte":
        verdict = "pass" if null_ratio <= target_value else "fail"
    elif comparator == "gte":
        verdict = "pass" if null_ratio >= target_value else "fail"
    else:
        verdict = "pass" if abs(null_ratio - target_value) < 0.001 else "fail"
    return verdict, {
        "observed": null_ratio,
        "target": target_value,
        "comparator": comparator,
    }


def measure_availability(
    factory: SessionFactory,
    *,
    data_product_id: int,
    target_value: float,
    comparator: str = "gte",
    window_days: int = 7,
) -> tuple[str, dict[str, Any]]:
    """Compute the rolling availability percentage from probe rows."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=window_days)
    with factory() as session:
        rows = session.scalars(
            select(DataProductAvailabilityProbe).where(
                DataProductAvailabilityProbe.data_product_id == data_product_id,
                DataProductAvailabilityProbe.probed_at >= cutoff,
            )
        ).all()
    if not rows:
        return "unmeasured", {"reason": "no probes in window"}
    total = len(rows)
    ok = sum(1 for r in rows if r.status == "ok")
    observed = (ok / total) * 100.0
    if comparator == "lte":
        verdict = "pass" if observed <= target_value else "fail"
    elif comparator == "gte":
        verdict = "pass" if observed >= target_value else "fail"
    else:
        verdict = "pass" if abs(observed - target_value) < 0.001 else "fail"
    return verdict, {
        "observed_percent": observed,
        "ok_count": ok,
        "total_count": total,
        "window_days": window_days,
    }


def measure_performance(
    factory: SessionFactory,
    *,
    data_product_id: int,
    target_value: float,
    comparator: str = "lte",
    sample_window: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Compute p95 query duration from the rolling perf-sample window."""
    with factory() as session:
        rows = session.scalars(
            select(DataProductQueryPerfSample)
            .where(
                DataProductQueryPerfSample.data_product_id == data_product_id,
                DataProductQueryPerfSample.status == "ok",
            )
            .order_by(DataProductQueryPerfSample.started_at.desc())
            .limit(sample_window)
        ).all()
    if not rows:
        return "unmeasured", {"reason": "no perf samples"}
    durations = sorted(float(r.duration_ms) for r in rows)
    p95 = _percentile_sorted(durations, 0.95)
    if comparator == "lte":
        verdict = "pass" if p95 <= target_value else "fail"
    elif comparator == "gte":
        verdict = "pass" if p95 >= target_value else "fail"
    else:
        verdict = "pass" if abs(p95 - target_value) < 0.001 else "fail"
    return verdict, {
        "observed_p95_ms": p95,
        "sample_count": len(rows),
    }


_DISPATCH = {
    "timeliness": "timeliness",
    "precision_accuracy": "precision_accuracy",
    "availability": "availability",
    "performance": "performance",
}


def measure_runtime_kind(
    factory: SessionFactory,
    *,
    kind: str,
    data_product_id: int,
    target_value: float,
    comparator: str,
    spec: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Dispatch one of the four runtime kinds.

    Args:
        factory: Sessionmaker callable.
        kind: One of the keys in :data:`_DISPATCH`.
        data_product_id: Product PK.
        target_value: Declared target.
        comparator: ``lte`` / ``gte`` / ``eq``.
        spec: Kind-specific extras (e.g. bitemporal columns).

    Returns:
        ``(verdict, detail)`` tuple.

    Raises:
        ValueError: When *kind* is outside the dispatch table.
    """
    spec = spec or {}
    if kind not in _DISPATCH:
        raise ValueError(f"unknown runtime kind: {kind!r}")
    if kind == "timeliness":
        return measure_timeliness(
            factory,
            data_product_id=data_product_id,
            event_time_col=spec.get("event_time_col"),
            processing_time_col=spec.get("processing_time_col"),
            target_value=target_value,
            comparator=comparator,
        )
    if kind == "precision_accuracy":
        return measure_precision_accuracy(
            factory,
            data_product_id=data_product_id,
            table_name=spec.get("table_name"),
            target_value=target_value,
            comparator=comparator,
        )
    if kind == "availability":
        return measure_availability(
            factory,
            data_product_id=data_product_id,
            target_value=target_value,
            comparator=comparator,
            window_days=int(spec.get("window_days", 7)),
        )
    return measure_performance(
        factory,
        data_product_id=data_product_id,
        target_value=target_value,
        comparator=comparator,
        sample_window=int(spec.get("sample_window", 100)),
    )
