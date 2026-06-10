"""DML dispatcher branches — INSERT / CTAS, UPDATE, DELETE, MERGE.

Each branch follows the same envelope: enforce SELECT on sources +
MODIFY on the target, open an editor agent_run, run the PQL
primitive in a thread, finalise the run with terminal status.  The
shared pattern lives inline rather than behind a context-manager
because the per-branch primitive call site differs enough that a
generic wrapper would obscure rather than clarify.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from sqlglot import expressions as exp

from pointlessql.api.sql._dispatcher._agent_run import (
    finish_agent_run,
    start_editor_agent_run,
)
from pointlessql.api.sql._dispatcher._ast_extract import (
    extract_source_select_sql,
    extract_update_args,
    extract_where_sql,
    int_or_none,
    merge_rows_affected,
)
from pointlessql.api.sql._dispatcher._privilege import (
    enforce_modify_target,
    enforce_select_per_table,
)
from pointlessql.api.sql._dispatcher._types import DispatchContext, ExecutionResult
from pointlessql.exceptions import SQLExecutionError
from pointlessql.pql import extract_source_refs, extract_write_target


async def execute_insert(
    ctx: DispatchContext,
    *,
    mode: Literal["append", "overwrite"],
    create_if_missing: bool = False,
) -> ExecutionResult:
    """Materialise the source SELECT and write to the target Delta table.

    Used by both ``INSERT INTO ... SELECT`` (mode='append') and
    ``CREATE TABLE ... AS SELECT`` (mode='overwrite').
    Source SELECT goes through the existing DuckDB rewriter; the
    materialised pandas frame is then handed to
    :meth:`PQL.write_table`, which emits the
    ``agent_run_operations`` row and any lineage edges.

    Args:
        ctx: Dispatcher context.
        mode: Delta write mode.
        create_if_missing: When ``True``, the primitive bootstraps
            a missing target from the parent schema's
            ``storage_root``.  CTAS sets this; INSERT does not.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and
        ``rows_affected`` from the materialised frame's row count.

    Raises:
        Exception: Any failure from the materialise/write primitive,
            re-raised verbatim after the agent_run is finalised as
            failed.
    """
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_sql = extract_source_select_sql(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)

    approved = await enforce_select_per_table(ctx, source_refs)
    target_exists = await enforce_modify_target(ctx, target_fqn, must_exist=not create_if_missing)
    if target_exists and create_if_missing and mode == "overwrite":
        # CTAS over an existing table: still allowed (overwrite),
        # but require MODIFY (already enforced) instead of just
        # CREATE_TABLE.  No further check needed.
        pass

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)
    op_name_label = "write_table"

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql.write import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
            _materialise_select_to_pandas,  # pyright: ignore[reportPrivateUsage]
        )

        df = _materialise_select_to_pandas(source_sql, approved)
        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        derived_source = source_refs[0] if len(source_refs) == 1 else None
        pql.write_table(
            df,
            target_fqn,
            mode=mode,
            source_table_fqn=derived_source,
        )
        rows = int(df.shape[0]) if hasattr(df, "shape") else len(df)
        return {"rows_affected": rows}

    try:
        info = await asyncio.to_thread(_run)
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=int(info.get("rows_affected", 0)),
        agent_run_id=run_id,
        op_name=op_name_label,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )


async def execute_update(ctx: DispatchContext) -> ExecutionResult:
    """Translate UPDATE AST → set_clause + WHERE → :meth:`PQL.update`.

    Args:
        ctx: Dispatcher context with the UPDATE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and
        ``rows_affected`` from deltalake's ``num_updated_rows``.

    Raises:
        Exception: Any failure from the update primitive, re-raised
            verbatim after the agent_run is finalised as failed.
    """
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    set_clause, where = extract_update_args(ctx.ast)

    if source_refs:
        await enforce_select_per_table(ctx, source_refs)
    await enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql.write import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
        )

        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        return pql.update(target_fqn, set_clause=set_clause, where=where)

    try:
        stats = await asyncio.to_thread(_run)
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=int_or_none(stats.get("num_updated_rows")),
        agent_run_id=run_id,
        op_name="update",
        stats=stats,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )


async def execute_delete(ctx: DispatchContext) -> ExecutionResult:
    """Translate DELETE AST → WHERE clause → :meth:`PQL.delete`.

    Args:
        ctx: Dispatcher context with the DELETE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and the
        deltalake delete metrics.

    Raises:
        Exception: Any failure from the delete primitive, re-raised
            verbatim after the agent_run is finalised as failed.
    """
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    where = extract_where_sql(ctx.ast)

    if source_refs:
        await enforce_select_per_table(ctx, source_refs)
    await enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql.write import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
        )

        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        return pql.delete(target_fqn, where=where)

    try:
        stats = await asyncio.to_thread(_run)
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=int_or_none(stats.get("num_deleted_rows")),
        agent_run_id=run_id,
        op_name="delete",
        stats=stats,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )


async def execute_merge(ctx: DispatchContext) -> ExecutionResult:
    """Translate MERGE AST → :class:`MergeCallSpec` → :meth:`PQL.merge`.

    The translator (:mod:`pointlessql.pql.sql_merge_translator`)
    raises :class:`SQLMergeUnsupportedError` for AST features
    outside
    the ``upsert`` / ``upsert + INSERT`` shape ``pql.merge``
    supports.

    Args:
        ctx: Dispatcher context with the MERGE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and the
        merge stats (insert / update counts).

    Raises:
        SQLExecutionError: When the dispatcher routed a non-MERGE
            AST here (defensive internal-error guard).
        Exception: Any translator or merge-primitive failure,
            re-raised verbatim after the agent_run is finalised as
            failed.
    """
    from pointlessql.pql import translate_merge_ast

    if not isinstance(ctx.ast, exp.Merge):  # defensive
        raise SQLExecutionError("Internal error: execute_merge invoked on non-Merge AST.")

    merge_ast: exp.Merge = ctx.ast
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    approved = await enforce_select_per_table(ctx, source_refs)
    await enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.sql.write import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
        )

        spec = translate_merge_ast(merge_ast, conn=ctx.conn, approved=approved)
        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        derived_source = source_refs[0] if len(source_refs) == 1 else None
        return pql.merge(
            spec.source_df,
            spec.target,
            on=spec.on,
            strategy=spec.strategy,
            source_table_fqn=derived_source,
        )

    try:
        stats = await asyncio.to_thread(_run)
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    rows_affected = merge_rows_affected(stats)
    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=rows_affected,
        agent_run_id=run_id,
        op_name="merge",
        stats=stats,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )
