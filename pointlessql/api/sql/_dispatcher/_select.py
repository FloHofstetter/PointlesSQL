"""SELECT dispatcher branch — kept separate to avoid the editor↔dispatcher cycle.

The SELECT path is the only branch that imports from
``api.sql.editor`` (to reuse the DuckDB rewriter wrapper).  Isolating
it here means the rest of ``_dispatcher`` stays decoupled from the
editor module, which makes test imports cheaper and avoids surprise
import cycles when the editor evolves.
"""

from __future__ import annotations

import asyncio

from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table
from pointlessql.api.sql._dispatcher._types import DispatchContext, ExecutionResult
from pointlessql.pql import prepare_sql


async def execute_select(ctx: DispatchContext) -> ExecutionResult:
    """Run a SELECT through the existing DuckDB rewriter path.

    Identical shape to the pre-Phase-63 ``api_sql_execute``
    SELECT body — kept here so the dispatcher owns 100% of the
    statement-type branching.

    Args:
        ctx: Dispatcher context with the SELECT AST.

    Returns:
        :class:`ExecutionResult` with ``kind='select'`` and the
        legacy SELECT fields populated.
    """
    from pointlessql.api.sql.editor import run_sql_sync

    prepared = prepare_sql(ctx.sql)
    approved = await enforce_select_per_table(ctx, prepared.refs)

    result = await asyncio.to_thread(
        run_sql_sync,
        ctx.settings,
        ctx.sql,
        approved,
        ctx.max_rows,
        ctx.conn,
        False,  # explain handled in the route
    )
    return ExecutionResult(
        kind="select",
        columns=list(result.columns),
        rows=list(result.rows),
        row_count=result.row_count,
        truncated=result.truncated,
        duration_ms=result.duration_ms,
        executed_sql=result.executed_sql,
        referenced_tables=list(result.referenced_tables),
    )
