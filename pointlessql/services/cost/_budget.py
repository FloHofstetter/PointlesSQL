"""Budget threshold evaluation — pure status decision.

Given a budget amount, warn/block thresholds, and the cost accrued so far,
decides the budget status and which signal (if any) to raise.  Pure: it
makes the decision from numbers, so the thresholds are auditable in one
place.  Persisting budgets, summing the hourly buckets, and emitting the
signal through the open-ledger / alert dispatcher are the caller's job
(deferred — the budget table + migration are not in this backbone).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

BudgetStatus = Literal["ok", "warn", "exhausted"]

_DEFAULT_WARN_PERCENT = 80.0
_DEFAULT_BLOCK_PERCENT = 100.0


@dataclass(frozen=True)
class BudgetEvaluation:
    """Outcome of evaluating cost-so-far against a budget.

    Attributes:
        status: ``ok`` / ``warn`` / ``exhausted``.
        percent_used: Cost-so-far as a percentage of the budget amount.
        signal_kind: The signal to raise (``budget_warn`` /
            ``budget_block``), or ``None`` when within budget.
    """

    status: BudgetStatus
    percent_used: float
    signal_kind: str | None


def evaluate_budget(
    accrued_cost: Decimal,
    budget_amount: Decimal,
    *,
    warn_percent: float = _DEFAULT_WARN_PERCENT,
    block_percent: float = _DEFAULT_BLOCK_PERCENT,
) -> BudgetEvaluation:
    """Decide the budget status for *accrued_cost* against *budget_amount*.

    Args:
        accrued_cost: Cost-so-far in the current budget period.
        budget_amount: The budget's total amount (must be positive).
        warn_percent: Percent-used at/above which to warn (default 80).
        block_percent: Percent-used at/above which the budget is exhausted
            (default 100).

    Returns:
        A :class:`BudgetEvaluation`.  A non-positive budget is treated as
        immediately exhausted once any cost is accrued.
    """
    if budget_amount <= 0:
        if accrued_cost > 0:
            return BudgetEvaluation("exhausted", 100.0, "budget_block")
        return BudgetEvaluation("ok", 0.0, None)
    percent = float(accrued_cost / budget_amount * 100)
    if percent >= block_percent:
        return BudgetEvaluation("exhausted", percent, "budget_block")
    if percent >= warn_percent:
        return BudgetEvaluation("warn", percent, "budget_warn")
    return BudgetEvaluation("ok", percent, None)
