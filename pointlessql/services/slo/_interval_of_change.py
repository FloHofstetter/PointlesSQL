"""Interval-of-change SLO measurement (G1).

Reads the ``data_product_contract_events`` table for one product and
computes the median + p95 of the time between consecutive write events
on the last *N* write outcomes.  Returns ``None`` when there are fewer
than two writes — the metric is undefined.

The result feeds :func:`pointlessql.services.slo._evaluate.evaluate_slo`
via a small bridge function in this module.
"""

from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProductContractEvent
from pointlessql.types import SessionFactory

#: Default window of recent write events to base the metric on.
DEFAULT_WINDOW_WRITES: int = 50

#: Outcomes that count as a write for the purpose of the metric.
#: All contract-event rows correspond to a write attempt; only the
#: ``violated`` outcome aborted on the schema-drift gate.
WRITE_OUTCOMES: tuple[str, ...] = (
    "compliant",
    "schema_drift_warning",
    "no_contract",
)


@dataclasses.dataclass(frozen=True)
class IntervalOfChangeMeasurement:
    """Result of one interval-of-change measurement.

    Attributes:
        median_minutes: Median interval between writes, in minutes.
        p95_minutes: 95th-percentile interval, in minutes.
        sample_size: Number of intervals the metrics were computed on
            (= write events - 1).
        last_write_at: ISO timestamp of the most recent write seen.
    """

    median_minutes: float
    p95_minutes: float
    sample_size: int
    last_write_at: str | None


def _percentile_sorted(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile on a *sorted* sequence."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * q
    lo_index = int(rank)
    hi_index = min(lo_index + 1, len(values) - 1)
    fraction = rank - lo_index
    return float(values[lo_index] * (1 - fraction) + values[hi_index] * fraction)


def measure_interval_of_change(
    factory: SessionFactory,
    *,
    data_product_id: int,
    window: int = DEFAULT_WINDOW_WRITES,
) -> IntervalOfChangeMeasurement | None:
    """Compute median + p95 inter-write intervals.

    Args:
        factory: Sessionmaker callable.
        data_product_id: Product PK to measure.
        window: Cap on most-recent write events to consider.

    Returns:
        :class:`IntervalOfChangeMeasurement` or ``None`` when fewer
        than two write events were found.

    Raises:
        ValueError: When ``window`` is < 2.
    """
    if window < 2:
        raise ValueError("window must be ≥ 2")
    with factory() as session:
        rows = session.scalars(
            select(DataProductContractEvent)
            .where(
                DataProductContractEvent.data_product_id == data_product_id,
                DataProductContractEvent.outcome.in_(list(WRITE_OUTCOMES)),
            )
            .order_by(DataProductContractEvent.created_at.desc())
            .limit(window)
        ).all()
    if len(rows) < 2:
        return None
    timestamps: list[datetime.datetime] = [r.created_at for r in rows]
    timestamps.sort()
    intervals: list[float] = []
    for prev, current in zip(timestamps, timestamps[1:]):
        intervals.append((current - prev).total_seconds() / 60.0)
    intervals.sort()
    return IntervalOfChangeMeasurement(
        median_minutes=_percentile_sorted(intervals, 0.5),
        p95_minutes=_percentile_sorted(intervals, 0.95),
        sample_size=len(intervals),
        last_write_at=timestamps[-1].isoformat(),
    )


def verdict_from_measurement(
    measurement: IntervalOfChangeMeasurement | None,
    *,
    target_value: float,
    comparator: str,
) -> tuple[str, dict[str, Any]]:
    """Translate a measurement into a verdict for the SLO evaluator.

    Args:
        measurement: Output of :func:`measure_interval_of_change`.
        target_value: Declared target (median-minutes ceiling when
            comparator is ``lte``).
        comparator: One of ``lte`` / ``gte`` / ``eq``.

    Returns:
        ``(verdict, detail_dict)`` where verdict is ``"pass"`` /
        ``"fail"`` / ``"unmeasured"``.
    """
    if measurement is None:
        return ("unmeasured", {"reason": "fewer than 2 write events"})

    observed = measurement.median_minutes
    if comparator == "lte":
        verdict = "pass" if observed <= target_value else "fail"
    elif comparator == "gte":
        verdict = "pass" if observed >= target_value else "fail"
    else:
        verdict = "pass" if abs(observed - target_value) < 0.001 else "fail"

    return (
        verdict,
        {
            "observed": observed,
            "p95_minutes": measurement.p95_minutes,
            "sample_size": measurement.sample_size,
            "last_write_at": measurement.last_write_at,
        },
    )
