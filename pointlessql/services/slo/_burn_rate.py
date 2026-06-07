"""SLO error-budget burn-rate — pure calculation, no I/O.

Given a history of SLO verdicts (``ok`` / ``not ok`` at a point in time),
computes the multi-window burn rate and the remaining error budget.  The
burn rate is the rate at which the error budget is being consumed relative
to the budget allowed by the target: a burn rate of ``1.0`` means the
budget is being spent exactly as fast as the SLO permits, ``> 1.0`` means
it will be exhausted before the window ends.

Two windows make alerting both fast and stable (the Google SRE
multi-window pattern): a short *fast* window (default 6 h) catches acute
outages quickly, while a long *slow* window (default 30 d) tracks the
overall budget and suppresses flapping.  Alert when **both** windows burn
hot.

This module is deliberately pure — it takes the verdict history and the
current time as arguments and returns a dataclass — so it is trivially
testable and free of any database or clock dependency.  Persistence of the
verdict history and the alerting decision live in the SLO evaluator and the
scheduler executor respectively.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

_FAST_WINDOW = timedelta(hours=6)
_SLOW_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class BurnRateResult:
    """Outcome of a burn-rate calculation.

    Attributes:
        burn_rate_fast: Burn rate over the fast window, or ``None`` when
            the window holds no verdicts.
        burn_rate_slow: Burn rate over the slow window, or ``None`` when
            the window holds no verdicts.
        budget_remaining: Fraction of the error budget still unspent over
            the slow window, in ``[0.0, 1.0]`` (``None`` if unmeasurable).
        fast_window_count: Number of verdicts in the fast window.
        slow_window_count: Number of verdicts in the slow window.
    """

    burn_rate_fast: float | None
    burn_rate_slow: float | None
    budget_remaining: float | None
    fast_window_count: int
    slow_window_count: int


def _error_rate(
    verdicts: Sequence[tuple[datetime, bool]], since: datetime
) -> tuple[float | None, int]:
    """Return ``(error_rate, count)`` for verdicts at or after *since*.

    Args:
        verdicts: ``(evaluated_at, ok)`` pairs; ``ok=False`` is a breach.
        since: Lower time bound (inclusive) for the window.

    Returns:
        The fraction of breaching verdicts in the window and the verdict
        count; ``(None, 0)`` when the window is empty.
    """
    in_window = [ok for (ts, ok) in verdicts if ts >= since]
    if not in_window:
        return None, 0
    breaches = sum(1 for ok in in_window if not ok)
    return breaches / len(in_window), len(in_window)


def calculate_burn_rate(
    verdicts: Sequence[tuple[datetime, bool]],
    *,
    now: datetime,
    slo_target: float,
    fast_window: timedelta = _FAST_WINDOW,
    slow_window: timedelta = _SLOW_WINDOW,
) -> BurnRateResult:
    """Compute the multi-window burn rate and remaining error budget.

    Args:
        verdicts: ``(evaluated_at, ok)`` pairs across the measurement
            history; order does not matter.
        now: The reference time the windows are measured back from.
        slo_target: The SLO success target as a fraction (``0.99`` for a
            99% objective).  The error budget is ``1 - slo_target``.
        fast_window: The short alerting window (default 6 h).
        slow_window: The long budget window (default 30 d).

    Returns:
        A :class:`BurnRateResult`.  A perfectly-met SLO yields burn rates
        of ``0.0`` and ``budget_remaining`` of ``1.0``; an SLO with a
        ``100%`` target (zero error budget) yields burn rates of ``0.0``
        while clean and a large finite rate once any breach appears.
    """
    error_budget = max(0.0, 1.0 - slo_target)

    fast_rate, fast_count = _error_rate(verdicts, now - fast_window)
    slow_rate, slow_count = _error_rate(verdicts, now - slow_window)

    burn_fast = _burn(fast_rate, error_budget)
    burn_slow = _burn(slow_rate, error_budget)

    if slow_rate is None:
        budget_remaining = None
    elif error_budget <= 0.0:
        budget_remaining = 1.0 if slow_rate == 0.0 else 0.0
    else:
        budget_remaining = max(0.0, 1.0 - (slow_rate / error_budget))

    return BurnRateResult(
        burn_rate_fast=burn_fast,
        burn_rate_slow=burn_slow,
        budget_remaining=budget_remaining,
        fast_window_count=fast_count,
        slow_window_count=slow_count,
    )


def _burn(error_rate: float | None, error_budget: float) -> float | None:
    """Return the burn rate, handling the zero-budget edge case.

    Args:
        error_rate: Observed error fraction in the window, or ``None``.
        error_budget: The allowed error fraction (``1 - target``).

    Returns:
        ``error_rate / error_budget`` normally; ``None`` for an empty
        window; ``0.0`` for a clean zero-budget SLO and ``inf`` once a
        zero-budget SLO records any breach.
    """
    if error_rate is None:
        return None
    if error_budget <= 0.0:
        return 0.0 if error_rate == 0.0 else float("inf")
    return error_rate / error_budget
