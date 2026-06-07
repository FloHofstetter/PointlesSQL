"""Cost forecasting — pure linear projection over a cost history.

Projects when a budget will be exhausted from a daily cost history using a
least-squares trend, and reports a confidence that reflects how much history
backs the estimate.  Pure: it takes ``(day_index, daily_cost)`` points and
the remaining budget, so the projection is testable without a database.
Reading the daily buckets and caching the forecast are the caller's job.

The forecast is deliberately humble: on sparse history (< a week of points)
it returns a low confidence so the UI does not over-promise an "N days"
estimate built on noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_MIN_POINTS_FOR_CONFIDENCE = 7


@dataclass(frozen=True)
class CostForecast:
    """A budget-exhaustion forecast.

    Attributes:
        days_to_breach: Projected days until the remaining budget is spent,
            or ``None`` when cost is flat/declining (never breaches) or
            there is too little history.
        daily_rate: The fitted average cost per day.
        confidence: ``0.0``–``1.0`` — how much history backs the estimate.
        message: A human-readable summary.
    """

    days_to_breach: int | None
    daily_rate: float
    confidence: float
    message: str


def _linear_rate(points: list[tuple[int, float]]) -> float:
    """Least-squares slope of cost vs day index (cost per day)."""
    n = len(points)
    if n < 2:
        return points[0][1] if points else 0.0
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return sy / n
    return (n * sxy - sx * sy) / denom


def forecast_breach(
    points: list[tuple[int, float]],
    remaining_budget: Decimal,
) -> CostForecast:
    """Forecast days until *remaining_budget* is exhausted.

    Args:
        points: ``(day_index, daily_cost)`` samples, oldest first.
        remaining_budget: Budget left to spend (cost units).

    Returns:
        A :class:`CostForecast`.  ``days_to_breach`` is ``None`` when no
        spend is observed (rate ≤ 0) or there is no data.  The spend rate
        is the mean daily cost; the fitted slope only colours the message
        (rising / falling), so a flat-but-positive spend still projects a
        breach.
    """
    if not points:
        return CostForecast(None, 0.0, 0.0, "no cost history yet")
    daily_rate = max(0.0, sum(y for _, y in points) / len(points))
    slope = _linear_rate(points)
    confidence = min(1.0, len(points) / _MIN_POINTS_FOR_CONFIDENCE)
    if daily_rate <= 0.0:
        return CostForecast(None, daily_rate, confidence, "no spend observed; no breach projected")
    days = int(float(remaining_budget) / daily_rate)
    trend = "rising" if slope > 0 else "falling" if slope < 0 else "flat"
    qualifier = "" if confidence >= 1.0 else " (low confidence — sparse history)"
    return CostForecast(
        days_to_breach=days,
        daily_rate=daily_rate,
        confidence=round(confidence, 2),
        message=f"budget reached in ~{days} day(s); spend {trend}{qualifier}",
    )
