"""Lens query cost gate — auto-LIMIT + EXPLAIN cost cap + session budget.

Every Lens ``query`` tool dispatch passes through :func:`gate_query`
before DuckDB execution.  The gate composes four checks in sequence:

1. **Read-only enforcement** — :func:`prepare_sql` rejects any
   non-SELECT statement at the AST level.
2. **Auto-LIMIT injection** — :func:`inject_limit` appends
   ``LIMIT N`` (default from settings) when absent.
3. **EXPLAIN cost cap** — :func:`estimate_cost` walks the plan tree
   and refuses queries above ``settings.lens.max_query_cost``.
4. **Session budget cap** — refuses if the session's accumulated
   cost would exceed ``settings.lens.max_session_cost``.

Failures raise typed exceptions so the audit-hook can stamp the
right ``tool_status`` (``cost_denied`` / ``session_budget_exceeded``
/ ``non_select_blocked``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.pql.sql_parser import (
    PreparedSQL,
    SQLParseError,
    inject_limit,
    prepare_sql,
)
from pointlessql.services.sql.cost_estimator import CostEstimate
from pointlessql.services.sql.explain import run_explain
from pointlessql.types import ErrorCode

DEFAULT_QUERY_LIMIT = 1000


class LensQueryTooCostlyError(ValidationError):
    """The estimated cost exceeds :class:`LensSettings.max_query_cost`.

    Status code 422 inherits from :class:`ValidationError`.

    Attributes:
        error_code: :data:`ErrorCode.LENS_QUERY_TOO_COSTLY`.
    """

    error_code: ErrorCode = ErrorCode.LENS_QUERY_TOO_COSTLY


class LensSessionBudgetExceededError(ValidationError):
    """The session's cumulative cost would exceed the per-session cap.

    Status code 422 inherits from :class:`ValidationError`.

    Attributes:
        error_code: :data:`ErrorCode.LENS_SESSION_BUDGET_EXCEEDED`.
    """

    error_code: ErrorCode = ErrorCode.LENS_SESSION_BUDGET_EXCEEDED


class LensNonSelectBlockedError(ValidationError):
    """The submitted SQL was not a SELECT (Lens is read-only).

    Status code 422 inherits from :class:`ValidationError`.

    Attributes:
        error_code: :data:`ErrorCode.LENS_NON_SELECT_BLOCKED`.
    """

    error_code: ErrorCode = ErrorCode.LENS_NON_SELECT_BLOCKED


@dataclass(frozen=True)
class GatedSql:
    """Output of :func:`gate_query` — ready for DuckDB execution.

    Attributes:
        prepared: :class:`PreparedSQL` from the AST validator (carries
            the rewritten SQL and the referenced-table list).
        sql: The SQL after auto-LIMIT injection (overrides
            ``prepared.rewritten_sql`` when LIMIT was added).
        cost: The :class:`CostEstimate` from the EXPLAIN walk.
    """

    prepared: PreparedSQL
    sql: str
    cost: CostEstimate


def gate_query(
    sql: str,
    *,
    approved_tables: dict[str, str],
    default_limit: int = DEFAULT_QUERY_LIMIT,
    max_query_cost: float,
    max_session_cost: float,
    session_cost_so_far: float,
) -> GatedSql:
    """Validate, LIMIT-inject, EXPLAIN, and budget-check *sql*.

    See module docstring for the four checks.  Failures raise typed
    exceptions; success returns the :class:`GatedSql` for execution.

    Args:
        sql: The SQL string to gate.
        approved_tables: Map of FQN → storage_location for every
            table the route already enforced SELECT on.  Empty dict
            is fine when the gate is invoked in isolation (tests).
        default_limit: LIMIT value to inject when SQL has none.
        max_query_cost: Per-query cost cap; queries above raise
            :class:`LensQueryTooCostlyError`.
        max_session_cost: Per-session cumulative cost cap; queries
            that would push the session above raise
            :class:`LensSessionBudgetExceededError`.
        session_cost_so_far: The session's accumulated cost so far.

    Returns:
        :class:`GatedSql` with the gated SQL + cost estimate.

    Raises:
        LensNonSelectBlockedError: The SQL is not a SELECT.
        LensQueryTooCostlyError: The plan cost exceeds the per-query
            cap.
        LensSessionBudgetExceededError: The plan cost would push the
            session over the per-session cap.
    """
    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise LensNonSelectBlockedError(
            f"Lens accepts SELECT only ({exc})"
        ) from exc

    limited = inject_limit(prepared.rewritten_sql, default_limit=default_limit)
    cost = _explain_cost_or_zero(limited, approved_tables)

    if cost.cost > max_query_cost:
        raise LensQueryTooCostlyError(
            f"Estimated cost {cost.cost:,} exceeds the per-query cap "
            f"{int(max_query_cost):,}.  {cost.explanation}",
        )

    if session_cost_so_far + cost.cost > max_session_cost:
        raise LensSessionBudgetExceededError(
            f"Adding cost {cost.cost:,} would push the session over "
            f"the {int(max_session_cost):,} budget cap "
            f"(spent {int(session_cost_so_far):,} so far).",
        )

    return GatedSql(prepared=prepared, sql=limited, cost=cost)


def _explain_cost_or_zero(
    sql: str, approved_tables: dict[str, str]
) -> CostEstimate:
    """Run EXPLAIN with a fail-soft fallback when no tables are approved.

    Tests often pass ``approved_tables={}`` to exercise the gate
    without spinning up DuckDB.  Returning ``CostEstimate(0, 0, 0)``
    on the empty case keeps the unit-test path cheap; production
    paths always populate ``approved_tables`` from the route's
    pre-flight SELECT enforcement.
    """
    if not approved_tables:
        return CostEstimate(max_cardinality=0, join_depth=0, cost=0)
    try:
        result = run_explain(sql, approved_tables)
    except PointlessSQLError:
        raise
    except Exception as exc:  # noqa: BLE001 — narrow-cast unknown EXPLAIN failures
        # Treat EXPLAIN parse drift as non-blocking: the executor will
        # still enforce timeouts; we just lose cost estimation for this
        # query.  Surface as zero so the budget check can't DOS the
        # analyst over a DuckDB version drift.
        _log_explain_drift(exc)
        return CostEstimate(max_cardinality=0, join_depth=0, cost=0)
    return result.cost


def _log_explain_drift(exc: Any) -> None:
    """Log that EXPLAIN parsing failed; cheap fall-through helper."""
    import logging

    logging.getLogger(__name__).warning(
        "Lens cost-gate: EXPLAIN parse failed (%s); proceeding without "
        "cost estimate.",
        exc,
    )
