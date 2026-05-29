"""SELECT dispatcher branch — kept separate to avoid the editor↔dispatcher cycle.

The SELECT path is the only branch that imports from
``api.sql.editor`` (to reuse the DuckDB rewriter wrapper).  Isolating
it here means the rest of ``_dispatcher`` stays decoupled from the
editor module, which makes test imports cheaper and avoids surprise
import cycles when the editor evolves.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pointlessql.api._consumption_hook import enforce_consumption_for_read
from pointlessql.api.dependencies import current_workspace_id, get_authoring_product, get_user
from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table
from pointlessql.api.sql._dispatcher._types import DispatchContext, ExecutionResult
from pointlessql.pql import prepare_sql
from pointlessql.services import governance as governance_service
from pointlessql.services.pii._redactor import get_or_create_pii_hash_secret


def _sql_strategies(factory: Any, approved: dict[str, str]) -> dict[str, str]:
    """Build a ``{column_name_lower: strategy}`` map for approved tables.

    Best-effort governance for the free-form SQL surface: a result
    column that still carries its source name gets masked.  A query
    that aliases or computes a classified column produces a name that
    no longer matches, so it slips through — exact masking only holds
    at the product's declared output ports.
    """
    strategies: dict[str, str] = {}
    index_cache: dict[tuple[str, str], dict[tuple[str, str], tuple[str, str]]] = {}
    for full_name in approved:
        parts = full_name.split(".")
        if len(parts) != 3:
            continue
        catalog, schema, table = parts
        key = (catalog, schema)
        if key not in index_cache:
            index_cache[key] = governance_service.classifications_for_schema(
                factory, catalog=catalog, schema=schema
            )
        for (tbl, column), (_cls, strategy) in index_cache[key].items():
            if tbl == table and strategy != "none":
                strategies[column.lower()] = strategy
    return strategies


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

    authoring_product_id = get_authoring_product(ctx.request)
    if authoring_product_id is not None:
        factory = ctx.request.app.state.session_factory
        workspace_id = current_workspace_id(ctx.request)
        user = get_user(ctx.request)
        for full_name in approved:
            enforce_consumption_for_read(
                ctx.request,
                factory=factory,
                workspace_id=workspace_id,
                user=user,
                authoring_product_id=authoring_product_id,
                source_fqn=full_name,
            )

    result = await asyncio.to_thread(
        run_sql_sync,
        ctx.settings,
        ctx.sql,
        approved,
        ctx.max_rows,
        ctx.conn,
        False,  # explain handled in the route
    )

    rows = list(result.rows)
    if not ctx.is_admin:
        factory = ctx.request.app.state.session_factory
        strategies = _sql_strategies(factory, approved)
        if strategies:
            secret = get_or_create_pii_hash_secret(factory)
            rows = governance_service.mask_sql_rows(
                list(result.columns), rows, strategies, unmask=False, secret=secret
            )

    return ExecutionResult(
        kind="select",
        columns=list(result.columns),
        rows=rows,
        row_count=result.row_count,
        truncated=result.truncated,
        duration_ms=result.duration_ms,
        executed_sql=result.executed_sql,
        referenced_tables=list(result.referenced_tables),
    )
