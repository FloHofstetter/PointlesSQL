"""DDL dispatcher branches — DROP TABLE, CREATE/DROP SCHEMA.

DDL flows through the soyuz facade instead of a PQL primitive, so
each branch records its own ``agent_run_operations`` row via
:func:`emit_ddl_op` for parity with DML.  Schema-level operations
are admin-only — the gate mirrors soyuz's own admin requirement.
"""

from __future__ import annotations

from pointlessql.api.dependencies import get_uc_client, require_admin
from pointlessql.api.sql._dispatcher._agent_run import (
    emit_ddl_op,
    finish_agent_run,
    start_editor_agent_run,
)
from pointlessql.api.sql._dispatcher._privilege import enforce_modify_target
from pointlessql.api.sql._dispatcher._types import DispatchContext, ExecutionResult
from pointlessql.pql import extract_write_target
from pointlessql.types import TableFqn


async def execute_drop_table(ctx: DispatchContext) -> ExecutionResult:
    """Drop a UC table via the soyuz facade (no Delta storage cleanup).

    Hive-style external-table semantics: the catalog row is
    removed but the Delta files stay on disk.  The editor
    confirmation modal spells this out so users do
    not expect a destructive bytes-level wipe.

    Args:
        ctx: Dispatcher context with the DROP TABLE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target=<full_name>``, and ``stats={'deleted': True}``.

    Raises:
        Exception: Re-raised soyuz facade failure, after the agent
            run is finalised as ``failed``.
    """
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    await enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)

    catalog, schema_name, table_name = TableFqn.parse(target_fqn).parts()
    uc_client = get_uc_client(ctx.request)

    try:
        await uc_client.delete_table(catalog, schema_name, table_name)
        await emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="drop_table",
            target_fqn=target_fqn,
            extras={"deleted": True},
        )
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="drop_table",
        stats={"deleted": True},
        executed_sql=ctx.sql,
    )


async def execute_create_schema(ctx: DispatchContext) -> ExecutionResult:
    """Create a UC schema via the soyuz facade.

    Admin-only — schema creation is a privileged operation
    matching soyuz's own gate.  Caller must pass
    :func:`require_admin` upstream of this branch.

    Args:
        ctx: Dispatcher context with the CREATE SCHEMA AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target='catalog.schema'``.

    Raises:
        Exception: Re-raised soyuz facade failure, after the agent
            run is finalised as ``failed``.
    """
    require_admin(ctx.request)
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    catalog, schema_name = target_fqn.split(".", 1)
    uc_client = get_uc_client(ctx.request)

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)
    try:
        await uc_client.create_schema(
            {"catalog_name": catalog, "name": schema_name},
        )
        await emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="create_schema",
            target_fqn=target_fqn,
            extras={"created": True},
        )
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="create_schema",
        stats={"created": True},
        executed_sql=ctx.sql,
    )


async def execute_drop_schema(ctx: DispatchContext) -> ExecutionResult:
    """Drop a UC schema via the soyuz facade — admin-only.

    Args:
        ctx: Dispatcher context with the DROP SCHEMA AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target='catalog.schema'``.

    Raises:
        Exception: Re-raised soyuz facade failure, after the agent
            run is finalised as ``failed``.
    """
    require_admin(ctx.request)
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    catalog, schema_name = target_fqn.split(".", 1)
    uc_client = get_uc_client(ctx.request)
    cascade = bool(getattr(ctx.ast, "args", {}).get("cascade", False))

    run_id = await start_editor_agent_run(ctx, target_fqn=target_fqn)
    try:
        await uc_client.delete_schema(catalog, schema_name, force=cascade)
        await emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="drop_schema",
            target_fqn=target_fqn,
            extras={"deleted": True, "cascade": cascade},
        )
        await finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="drop_schema",
        stats={"deleted": True, "cascade": cascade},
        executed_sql=ctx.sql,
    )
