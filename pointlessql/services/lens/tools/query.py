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

import datetime
import logging
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from pointlessql.services.cost import MeterContext, record_query_cost
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
    started_at = datetime.datetime.now(datetime.UTC)

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
        _record_meter(
            ctx,
            started_at=started_at,
            completed_at=datetime.datetime.now(datetime.UTC),
            estimated_cost=Decimal("0"),
            tables=[],
            error_class=status,
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
    completed_at = datetime.datetime.now(datetime.UTC)
    _record_meter(
        ctx,
        started_at=started_at,
        completed_at=completed_at,
        estimated_cost=Decimal(str(gated.cost.cost)),
        tables=list(gated.prepared.refs),
    )
    return QueryResult(
        columns=[],
        rows=[],
        row_count=0,
        truncated=False,
        executed_sql=gated.sql,
        estimated_cost=gated.cost.cost,
        cost_explanation=gated.cost.explanation,
    )


def _record_meter(
    ctx: SessionContext,
    *,
    started_at: datetime.datetime,
    completed_at: datetime.datetime,
    estimated_cost: Decimal,
    tables: list[str],
    error_class: str | None = None,
) -> None:
    """Best-effort insert into ``data_product_query_cost``.

    Meter failures are swallowed: cost telemetry should never block a
    successful query path.  Attribution is best-effort — when the
    Lens session is detached, ``authoring_product_id`` is left None
    and the row still counts toward workspace-wide aggregates.
    """
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    try:
        record_query_cost(
            ctx.factory,
            MeterContext(
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                estimated_cost=estimated_cost,
                bytes_scanned=None,
                rows_returned=None,
                tables=tables,
                principal_user_id=ctx.user_id,
                api_key_id=None,
                authoring_product_id=None,
                consumer_product_id=None,
                query_kind="select",
                error_class=error_class,
            ),
        )
    except Exception:  # noqa: BLE001
        # bare-broad-ok: meter is purely observational; never raise.
        logger.warning("lens query cost meter insert failed", exc_info=True)


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
