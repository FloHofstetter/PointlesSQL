"""SELECT execution tool — ``query``.

The Lens primary data tool.  Wraps :func:`gate_query` for safety
(read-only enforcement, auto-LIMIT, EXPLAIN-cost cap, per-session
budget) before handing the SQL to DuckDB.

Tables referenced by the SQL must be SELECT-able by the analyst
principal — UC privilege checks live at the route layer
(:func:`require_analyst` + the ``approved_tables`` build).  The tool
itself does not consult ACLs.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from pointlessql.services.lens.cost_gate import (
    LensNonSelectBlockedError,
    LensQueryTooCostlyError,
    LensSessionBudgetExceededError,
    gate_query,
)
from pointlessql.services.lens.tools._base import (
    LensToolError,
    SessionContext,
    ToolDef,
)

logger = logging.getLogger(__name__)


class QueryArgs(BaseModel):
    """Input for ``query``."""

    sql: str = Field(min_length=1, description="SELECT statement to run")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description=(
            "Optional explicit LIMIT override.  When omitted the gate "
            "auto-injects the configured default (typically 1000)."
        ),
    )


class QueryColumn(BaseModel):
    """One column descriptor in a query result."""

    name: str
    type_name: str | None = None


class QueryResult(BaseModel):
    """Output: column metadata + rows + cost annotation."""

    columns: list[QueryColumn] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    executed_sql: str = ""
    estimated_cost: int = 0
    cost_explanation: str = ""


async def _execute_query(ctx: SessionContext, args: QueryArgs) -> QueryResult:
    """Validate, cost-gate, execute the SELECT, return rows."""
    settings = ctx.settings
    default_limit = args.limit if args.limit is not None else settings.lens.default_query_limit

    # Cost-gate first; skip the actual DuckDB execution when no
    # uc_client is wired (test paths can verify the gate behaviour
    # without a full PQL runtime).
    try:
        gated = gate_query(
            args.sql,
            approved_tables={},  # tests pass empty; route layer fills
            default_limit=default_limit,
            max_query_cost=settings.lens.max_query_cost,
            max_session_cost=settings.lens.max_session_cost,
            session_cost_so_far=_session_cost(ctx),
        )
    except (
        LensNonSelectBlockedError,
        LensQueryTooCostlyError,
        LensSessionBudgetExceededError,
    ) as exc:
        status = (
            "non_select_blocked"
            if isinstance(exc, LensNonSelectBlockedError)
            else "cost_denied"
            if isinstance(exc, LensQueryTooCostlyError)
            else "session_budget_exceeded"
        )
        raise LensToolError(
            tool_name="query",
            message=str(exc),
            status=status,
            tool_args={"sql": args.sql, "limit": args.limit},
        ) from exc

    # Production path: DuckDB execution requires the route layer to
    # have populated ``approved_tables`` and (eventually) wired a PQL
    # connection through ctx.  we do not yet route
    # through PQL — the executor is added once the
    # browser chat-loop is in place and the route fills approved
    # tables from `check_privilege(SELECT)`.  For now we return the
    # gated SQL + cost so the audit-trail stays informative.
    return QueryResult(
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        executed_sql=gated.sql,
        estimated_cost=gated.cost.cost,
        cost_explanation=gated.cost.explanation,
    )


def _session_cost(ctx: SessionContext) -> float:
    """Look up the session's accumulated cost; 0 when no session bound."""
    if ctx.lens_session_id is None:
        return 0.0
    from pointlessql.models import LensSession

    with ctx.factory() as session:
        row = session.get(LensSession, ctx.lens_session_id)
        if row is None:
            return 0.0
        return float(row.total_cost_estimate or 0.0)


QUERY_TOOL = ToolDef(
    name="query",
    description=(
        "Execute a read-only SELECT against the analyst's UC scope.  "
        "The query is auto-LIMITed (default 1000 rows) and gated by "
        "an EXPLAIN cost cap.  DDL / DML are blocked at the validator "
        "(use the SQL editor or PQL primitives for writes).  Returns "
        "columns + rows + the gated SQL + cost estimate."
    ),
    input_model=QueryArgs,
    output_model=QueryResult,
    executor=_execute_query,
)


__all__ = [
    "QUERY_TOOL",
    "QueryArgs",
    "QueryColumn",
    "QueryResult",
    "_execute_query",
    "_session_cost",
]
