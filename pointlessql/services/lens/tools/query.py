"""SELECT execution tool — ``query``.

The Lens primary data tool.  Wraps :func:`gate_query` for safety
(read-only enforcement, auto-LIMIT, EXPLAIN-cost cap, per-session
budget) and then executes the gated SELECT against an in-process
DuckDB that has each referenced Delta table registered under its
verbatim ``catalog.schema.table`` name.

Governance: every referenced table is **masked at the source** before
it enters DuckDB — each table's classified columns are redacted via the
same ``governance.mask_dataframe`` sidecar the file-export port uses, so
the masking survives arbitrary joins / aggregations the LLM writes
downstream.  A non-admin analyst therefore never receives cleartext for
a classified column, no matter how the query reshapes it.  Stewards who
need cleartext use the per-product export instead; the conservative
``unmask = is_admin`` rule holds here because a Lens query may span
several products at once.

When no UC client is wired (``ctx.uc_client is None`` — unit tests and
detached gate checks) the tool stops after gating and returns the gated
SQL + cost estimate with no rows, so the audit trail stays informative
without a live runtime.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from pointlessql.exceptions import AuthorizationError
from pointlessql.services.authorization import SELECT, check_privilege
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

    # With a live UC client (production browser / MCP path) resolve each
    # referenced table to a storage location after a SELECT-privilege
    # check, so the cost gate's EXPLAIN runs on real tables and the
    # executor can read them.  Tests pass uc_client=None and stay on the
    # gated-SQL-only path further down.
    email, is_admin = ("", False)
    approved_tables: dict[str, str] = {}
    if ctx.uc_client is not None:
        email, is_admin = _principal_identity(ctx)
        approved_tables = await _resolve_and_authorise(ctx, args.sql, email, is_admin)

    try:
        gated = gate_query(
            args.sql,
            approved_tables=approved_tables,
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

    if ctx.uc_client is None:
        # No runtime wired (tests / detached gate check): return the
        # gated SQL + cost so the audit trail stays informative.
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

    # Production path: read + mask each referenced table, register it
    # into an in-process DuckDB, run the gated SQL, return the rows.
    columns, rows, truncated = await asyncio.to_thread(
        _run_duckdb, ctx, gated, approved_tables, default_limit, is_admin
    )
    _record_meter(
        ctx,
        started_at=started_at,
        completed_at=datetime.datetime.now(datetime.UTC),
        estimated_cost=Decimal(str(gated.cost.cost)),
        tables=list(gated.prepared.refs),
    )
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        executed_sql=gated.sql,
        estimated_cost=gated.cost.cost,
        cost_explanation=gated.cost.explanation,
    )


async def _resolve_and_authorise(
    ctx: SessionContext, sql: str, email: str, is_admin: bool
) -> dict[str, str]:
    """Parse *sql*, SELECT-gate each referenced table, resolve locations.

    Returns the ``FQN -> storage_location`` map the cost gate + executor
    need.  Raises a typed :class:`LensToolError` (so the chat-loop can
    surface a clean tool-error to the model) for non-SELECT input, an
    access denial, a non-3-part reference, or an unresolvable location.
    """
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    try:
        prepared = prepare_sql(sql)
    except SQLParseError as exc:
        raise LensToolError(
            tool_name="query",
            message=f"Lens accepts SELECT only ({exc})",
            status="non_select_blocked",
            tool_args={"sql": sql},
        ) from exc

    approved: dict[str, str] = {}
    assert ctx.uc_client is not None  # noqa: S101 — caller guarantees a live client
    for fqn in prepared.refs:
        parts = fqn.split(".")
        if len(parts) != 3:
            raise LensToolError(
                tool_name="query",
                message=f"table reference {fqn!r} must be a 3-part catalog.schema.table name",
                status="error",
                tool_args={"sql": sql},
            )
        try:
            await check_privilege(ctx.uc_client, email, is_admin, "table", fqn, SELECT)
        except AuthorizationError as exc:
            raise LensToolError(
                tool_name="query",
                message=f"You don't have SELECT on {fqn} ({exc})",
                status="access_denied",
                tool_args={"sql": sql},
            ) from exc
        info = await ctx.uc_client.get_table(parts[0], parts[1], parts[2])
        location = info.get("storage_location") if isinstance(info, dict) else None
        if not location:
            raise LensToolError(
                tool_name="query",
                message=f"table {fqn!r} has no resolvable storage location",
                status="error",
                tool_args={"sql": sql},
            )
        approved[fqn] = location
    return approved


def _run_duckdb(
    ctx: SessionContext,
    gated: Any,
    approved_tables: dict[str, str],
    limit: int,
    is_admin: bool,
) -> tuple[list[QueryColumn], list[list[Any]], bool]:
    """Read + mask each referenced table, run the gated SQL in DuckDB.

    Blocking — invoked via ``asyncio.to_thread``.  Each table is read
    straight from the storage location the caller already resolved +
    SELECT-gated, masked at the source (so classified columns stay
    redacted through any downstream join / aggregation), and registered
    into a connection-scoped DuckDB view at its verbatim FQN, which the
    gated SQL references.  ``unmask = is_admin`` keeps the rule
    conservative for cross-product queries — the read uses the
    already-authorised location, so it needs no further principal hop.
    """
    import deltalake
    import duckdb

    from pointlessql.services import governance as governance_service
    from pointlessql.services.pii._redactor import get_or_create_pii_hash_secret

    unmask = is_admin
    secret = None if unmask else get_or_create_pii_hash_secret(ctx.factory)

    conn = duckdb.connect()
    try:
        for fqn, location in approved_tables.items():
            _catalog, _schema, table = fqn.split(".")
            class_index = governance_service.classifications_for_schema(
                ctx.factory, catalog=_catalog, schema=_schema
            )
            strategies = {
                column: strategy
                for (tbl, column), (_cls, strategy) in class_index.items()
                if tbl == table
            }
            frame = deltalake.DeltaTable(location).to_pandas()
            frame = governance_service.mask_dataframe(
                frame, strategies, unmask=unmask, secret=secret
            )
            conn.register(fqn, _to_arrow(frame))
        arrow = conn.execute(gated.sql).to_arrow_table()
    finally:
        conn.close()

    names = [field.name for field in arrow.schema]
    columns = [QueryColumn(name=field.name, type_name=str(field.type)) for field in arrow.schema]
    rows = [[_json_safe(record.get(name)) for name in names] for record in arrow.to_pylist()]
    return columns, rows, len(rows) >= limit


def _to_arrow(frame: Any) -> Any:
    """Coerce an engine-native frame to a PyArrow table for DuckDB register.

    ``mask_dataframe`` yields a pandas frame when masking is active and
    the original engine frame otherwise; this normalises pandas /
    polars / pyarrow / duckdb-relation shapes to the one type DuckDB's
    ``register`` consumes uniformly.
    """
    import pyarrow as pa

    if isinstance(frame, pa.Table):
        return frame
    if hasattr(frame, "to_arrow_table"):  # duckdb relation
        return frame.to_arrow_table()
    if hasattr(frame, "to_arrow"):  # polars
        return frame.to_arrow()
    return pa.Table.from_pandas(frame, preserve_index=False)


def _json_safe(value: Any) -> Any:
    """Coerce one DuckDB cell to a JSON-native value.

    The result rides back through ``model_dump`` + ``json.dumps`` in the
    audit hook and the transport, so timestamps / decimals / bytes must
    not survive as native objects.  ``NaN`` collapses to ``None`` so the
    payload stays valid JSON.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return str(value)


def _principal_identity(ctx: SessionContext) -> tuple[str, bool]:
    """Resolve ``(email, is_admin)`` for ``ctx.user_id``; ``("", False)`` when absent."""
    if ctx.user_id is None:
        return "", False
    from pointlessql.models import User

    with ctx.factory() as session:
        user = session.get(User, ctx.user_id)
        if user is None:
            return "", False
        return user.email, bool(user.is_admin)


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
