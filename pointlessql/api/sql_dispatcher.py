"""Dispatch a single SQL statement to its typed primitive (Phase 63.4).

The SQL editor's ``POST /api/sql/execute`` route used to be a
SELECT-only runner that parsed → enforced ``SELECT`` per table →
executed against DuckDB.  Phase 63 turns it into an
AST-classifying **dispatcher** that routes each statement family
to its correct primitive:

* ``SELECT`` / ``WITH ... SELECT`` → DuckDB rewriter (today's path).
* ``INSERT INTO ... SELECT`` → :meth:`PQL.write_table(mode='append')`.
* ``CREATE TABLE ... AS SELECT`` → :meth:`PQL.write_table(mode='overwrite')`.
* ``UPDATE`` → :meth:`PQL.update`.
* ``DELETE`` → :meth:`PQL.delete`.
* ``MERGE`` → :func:`translate_merge_ast` → :meth:`PQL.merge`
  (Phase 63.5).
* ``DROP TABLE`` → ``soyuz.delete_table``.
* ``CREATE/DROP SCHEMA`` → ``soyuz.create_schema`` / ``soyuz.delete_schema``.
* ``ALTER TABLE`` → currently rejected with a structured "use the
  table-detail UI" error (Phase 63.3 deferred — needs cross-repo
  soyuz ``update_table`` route).

Audit semantics:

* SELECT keeps today's behaviour — no agent_run row is created.
  Only ``query_history`` records the read.
* Every write statement opens a one-shot ``agent_run`` with
  ``agent_id='sql-editor'`` BEFORE invoking the primitive.  The
  primitives (``write_table`` / ``update`` / ``delete`` / etc.)
  emit ``agent_run_operations`` against that run id automatically
  via :func:`pointlessql.services.agent_runs.operation_context`.
* ``query_history.agent_run_id`` is populated for write statements
  so ``/runs/<id>`` can surface the originating SQL (wired in
  Phase 63.8).

Privilege model mirrors the existing ``/api/pql/*`` write routes:

* SELECT path: per-table ``SELECT`` (today's loop).
* INSERT / CTAS / UPDATE / DELETE / MERGE: ``SELECT`` on source
  refs + ``MODIFY`` (or ``USE_SCHEMA`` for new-target CTAS) on
  target.
* DROP TABLE: ``MODIFY`` on target.
* CREATE/DROP SCHEMA: caller must be admin (matches the soyuz
  facade gates).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Request
from sqlglot import expressions as exp
from sqlglot.expressions.core import Expression

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.config import Settings
from pointlessql.exceptions import (
    CatalogNotFoundError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.models.agent_runs import STATUS_RUNNING, AgentRun
from pointlessql.pql.sql_parser import (
    PreparedSQL,
    StmtType,
    extract_source_refs,
    extract_write_target,
    prepare_sql,
)
from pointlessql.services.authorization import (
    MODIFY,
    SELECT,
    USE_SCHEMA,
    check_privilege,
)
from pointlessql.types import TableFqn

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Uniform return shape for every dispatcher branch.

    ``kind`` discriminates the JSON response shape the route
    returns; SELECT keeps the legacy ``columns/rows/row_count``
    fields, write paths add ``target``, ``rows_affected``,
    ``agent_run_id``, and ``operation_id``.
    """

    kind: Literal["select", "dml", "ddl"]
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int | None = None
    truncated: bool = False
    duration_ms: int | None = None
    executed_sql: str | None = None
    referenced_tables: list[str] = field(default_factory=list[str])
    target: str | None = None
    rows_affected: int | None = None
    agent_run_id: str | None = None
    operation_id: str | None = None
    op_name: str | None = None
    stats: dict[str, Any] | None = None


@dataclass
class DispatchContext:
    """Inputs assembled once at the route boundary.

    Avoids threading 8+ kwargs through every branch.
    """

    request: Request
    settings: Settings
    sql: str
    ast: Expression
    stype: StmtType
    actor_email: str
    is_admin: bool
    # duckdb.DuckDBPyConnection — Any so non-DuckDB branches may pass None
    conn: Any
    max_rows: int


async def dispatch(
    *,
    request: Request,
    settings: Settings,
    sql: str,
    ast: Expression,
    stype: StmtType,
    conn: Any,
) -> ExecutionResult:
    """Route *ast* to its typed primitive and return the result.

    Single dispatcher entry point used by
    :func:`pointlessql.api.sql_routes.api_sql_execute`.  Each
    branch handles its own privilege check, primitive call, and
    operation/lineage emission via
    :func:`pointlessql.services.agent_runs.operation_context`.

    Args:
        request: Incoming FastAPI request.
        settings: Application settings.
        sql: Original SQL text (used for hashing + agent_run row).
        ast: Parsed sqlglot expression.
        stype: Classification from :func:`classify`.
        conn: DuckDB connection (used by SELECT + source-SELECT
            materialisation in INSERT/CTAS/MERGE).

    Returns:
        An :class:`ExecutionResult` carrying either the SELECT
        rows or the write-result envelope.

    Raises:
        SQLExecutionError: Parse / dispatch / primitive failures.
        AuthorizationError: When the caller lacks the required
            privilege on a referenced table.
        CatalogNotFoundError: When a referenced table is unknown.
    """  # noqa: DOC502,DOC503 — exceptions propagate from helpers
    user = get_user(request)
    actor_email = effective_principal(request) or user.get("email", "")
    is_admin = bool(user.get("is_admin", False))
    ctx = DispatchContext(
        request=request,
        settings=settings,
        sql=sql,
        ast=ast,
        stype=stype,
        actor_email=actor_email,
        is_admin=is_admin,
        conn=conn,
        max_rows=settings.sql.max_rows,
    )

    if stype is StmtType.SELECT:
        return await _execute_select(ctx)
    if stype is StmtType.INSERT_FROM_SELECT:
        return await _execute_insert(ctx, mode="append")
    if stype is StmtType.CREATE_TABLE_AS:
        return await _execute_insert(ctx, mode="overwrite", create_if_missing=True)
    if stype is StmtType.UPDATE:
        return await _execute_update(ctx)
    if stype is StmtType.DELETE:
        return await _execute_delete(ctx)
    if stype is StmtType.MERGE:
        return await _execute_merge(ctx)
    if stype is StmtType.DROP_TABLE:
        return await _execute_drop_table(ctx)
    if stype is StmtType.CREATE_SCHEMA:
        return await _execute_create_schema(ctx)
    if stype is StmtType.DROP_SCHEMA:
        return await _execute_drop_schema(ctx)
    if stype is StmtType.ALTER_TABLE:
        # 63.3 deferred — soyuz facade does not yet expose
        # ``update_table``.  Keep the parser path live so the
        # editor surfaces a friendly "use the table-detail UI"
        # message instead of a generic parse error.
        raise SQLExecutionError(
            "ALTER TABLE is not yet supported from the SQL editor. "
            "Use the table-detail UI's edit form to change comments, "
            "tags, or properties.",
        )
    raise SQLExecutionError(f"Unsupported dispatcher path for stype={stype!r}.")


# ─── SELECT ──────────────────────────────────────────────────────────


async def _execute_select(ctx: DispatchContext) -> ExecutionResult:
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
    from pointlessql.api.sql_routes import run_sql_sync

    prepared = prepare_sql(ctx.sql)
    approved = await _enforce_select_per_table(ctx, prepared.refs)

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


# ─── INSERT FROM SELECT + CREATE TABLE AS SELECT ──────────────────────


async def _execute_insert(
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
    """  # noqa: DOC501,DOC503 — primitive failures propagate after agent_run finalisation
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_sql = _extract_source_select_sql(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)

    approved = await _enforce_select_per_table(ctx, source_refs)
    target_exists = await _enforce_modify_target(
        ctx, target_fqn, must_exist=not create_if_missing
    )
    if target_exists and create_if_missing and mode == "overwrite":
        # CTAS over an existing table: still allowed (overwrite),
        # but require MODIFY (already enforced) instead of just
        # CREATE_TABLE.  No further check needed.
        pass

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)
    op_name_label = "write_table"

    def _run() -> dict[str, Any]:
        from pointlessql.api.pql_write_routes import (
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
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
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


# ─── UPDATE ───────────────────────────────────────────────────────────


async def _execute_update(ctx: DispatchContext) -> ExecutionResult:
    """Translate UPDATE AST → set_clause + WHERE → :meth:`PQL.update`.

    Args:
        ctx: Dispatcher context with the UPDATE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and
        ``rows_affected`` from deltalake's ``num_updated_rows``.
    """  # noqa: DOC501,DOC503 — primitive failures propagate after agent_run finalisation
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    set_clause, where = _extract_update_args(ctx.ast)

    if source_refs:
        await _enforce_select_per_table(ctx, source_refs)
    await _enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.pql_write_routes import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
        )

        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        return pql.update(target_fqn, set_clause=set_clause, where=where)

    try:
        stats = await asyncio.to_thread(_run)
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=_int_or_none(stats.get("num_updated_rows")),
        agent_run_id=run_id,
        op_name="update",
        stats=stats,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )


# ─── DELETE ───────────────────────────────────────────────────────────


async def _execute_delete(ctx: DispatchContext) -> ExecutionResult:
    """Translate DELETE AST → WHERE clause → :meth:`PQL.delete`.

    Args:
        ctx: Dispatcher context with the DELETE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and the
        deltalake delete metrics.
    """  # noqa: DOC501,DOC503 — primitive failures propagate after agent_run finalisation
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    where = _extract_where_sql(ctx.ast)

    if source_refs:
        await _enforce_select_per_table(ctx, source_refs)
    await _enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.pql_write_routes import (
            _build_pql,  # pyright: ignore[reportPrivateUsage]
        )

        pql = _build_pql(ctx.request, principal=ctx.actor_email, agent_run_id=run_id)
        return pql.delete(target_fqn, where=where)

    try:
        stats = await asyncio.to_thread(_run)
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="dml",
        target=target_fqn,
        rows_affected=_int_or_none(stats.get("num_deleted_rows")),
        agent_run_id=run_id,
        op_name="delete",
        stats=stats,
        executed_sql=ctx.sql,
        referenced_tables=source_refs,
    )


# ─── MERGE ────────────────────────────────────────────────────────────


async def _execute_merge(ctx: DispatchContext) -> ExecutionResult:
    """Translate MERGE AST → :class:`MergeCallSpec` → :meth:`PQL.merge`.

    The translator (Phase 63.5,
    :mod:`pointlessql.pql.sql_merge_translator`) raises
    :class:`SQLMergeUnsupportedError` for AST features outside
    the ``upsert`` / ``upsert + INSERT`` shape ``pql.merge``
    supports.

    Args:
        ctx: Dispatcher context with the MERGE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='dml'`` and the
        merge stats (insert / update counts).
    """  # noqa: DOC501,DOC503 — translator + primitive failures propagate after agent_run finalisation
    from pointlessql.pql.sql_merge_translator import translate_merge_ast

    if not isinstance(ctx.ast, exp.Merge):  # defensive
        raise SQLExecutionError("Internal error: _execute_merge invoked on non-Merge AST.")

    merge_ast: exp.Merge = ctx.ast
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    source_refs = extract_source_refs(ctx.ast, ctx.stype)
    approved = await _enforce_select_per_table(ctx, source_refs)
    await _enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)

    def _run() -> dict[str, Any]:
        from pointlessql.api.pql_write_routes import (
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
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    rows_affected = _merge_rows_affected(stats)
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


# ─── DROP TABLE ───────────────────────────────────────────────────────


async def _execute_drop_table(ctx: DispatchContext) -> ExecutionResult:
    """Drop a UC table via the soyuz facade (no Delta storage cleanup).

    Hive-style external-table semantics: the catalog row is
    removed but the Delta files stay on disk.  The editor
    confirmation modal in Phase 63.7 spells this out so users do
    not expect a destructive bytes-level wipe.

    Args:
        ctx: Dispatcher context with the DROP TABLE AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target=<full_name>``, and ``stats={'deleted': True}``.
    """  # noqa: DOC501,DOC503 — soyuz failures propagate after agent_run finalisation
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    await _enforce_modify_target(ctx, target_fqn, must_exist=True)

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)

    catalog, schema_name, table_name = TableFqn.parse(target_fqn).parts()
    uc_client = get_uc_client(ctx.request)

    try:
        await uc_client.delete_table(catalog, schema_name, table_name)
        await _emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="drop_table",
            target_fqn=target_fqn,
            extras={"deleted": True},
        )
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="drop_table",
        stats={"deleted": True},
        executed_sql=ctx.sql,
    )


# ─── CREATE / DROP SCHEMA ─────────────────────────────────────────────


async def _execute_create_schema(ctx: DispatchContext) -> ExecutionResult:
    """Create a UC schema via the soyuz facade.

    Admin-only — schema creation is a privileged operation
    matching soyuz's own gate.  Caller must pass
    :func:`require_admin` upstream of this branch.

    Args:
        ctx: Dispatcher context with the CREATE SCHEMA AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target='catalog.schema'``.
    """  # noqa: DOC501,DOC503 — soyuz failures propagate after agent_run finalisation
    require_admin(ctx.request)
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    catalog, schema_name = target_fqn.split(".", 1)
    uc_client = get_uc_client(ctx.request)

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)
    try:
        await uc_client.create_schema(
            {"catalog_name": catalog, "name": schema_name},
        )
        await _emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="create_schema",
            target_fqn=target_fqn,
            extras={"created": True},
        )
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="create_schema",
        stats={"created": True},
        executed_sql=ctx.sql,
    )


async def _execute_drop_schema(ctx: DispatchContext) -> ExecutionResult:
    """Drop a UC schema via the soyuz facade — admin-only.

    Args:
        ctx: Dispatcher context with the DROP SCHEMA AST.

    Returns:
        :class:`ExecutionResult` with ``kind='ddl'``,
        ``target='catalog.schema'``.
    """  # noqa: DOC501,DOC503 — soyuz failures propagate after agent_run finalisation
    require_admin(ctx.request)
    target_fqn = extract_write_target(ctx.ast, ctx.stype)
    catalog, schema_name = target_fqn.split(".", 1)
    uc_client = get_uc_client(ctx.request)
    cascade = bool(getattr(ctx.ast, "args", {}).get("cascade", False))

    run_id = await _start_editor_agent_run(ctx, target_fqn=target_fqn)
    try:
        await uc_client.delete_schema(catalog, schema_name, force=cascade)
        await _emit_ddl_op(
            ctx,
            run_id=run_id,
            op_name_value="drop_schema",
            target_fqn=target_fqn,
            extras={"deleted": True, "cascade": cascade},
        )
        await _finish_agent_run(ctx, run_id, status="succeeded")
    except Exception as exc:
        await _finish_agent_run(ctx, run_id, status="failed", error=str(exc))
        raise

    return ExecutionResult(
        kind="ddl",
        target=target_fqn,
        agent_run_id=run_id,
        op_name="drop_schema",
        stats={"deleted": True, "cascade": cascade},
        executed_sql=ctx.sql,
    )


# ─── helpers ──────────────────────────────────────────────────────────


async def _enforce_select_per_table(
    ctx: DispatchContext, refs: list[str]
) -> dict[str, str]:
    """Run ``SELECT`` enforcement on every ref and return storage map.

    Args:
        ctx: Dispatcher context.
        refs: 3-part table names to enforce.

    Returns:
        Mapping ``full_name → storage_location`` for every ref.

    Raises:
        SQLExecutionError: When a ref is not 3-part qualified.
        CatalogNotFoundError: When a ref is unknown.
        AuthorizationError: When the caller lacks ``SELECT``.
    """  # noqa: DOC502,DOC503
    uc_client = get_uc_client(ctx.request)
    approved: dict[str, str] = {}
    for full_name in refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            raise SQLExecutionError(
                f"Internal error: expected 3-part name, got {full_name!r}.",
            )
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            raise CatalogNotFoundError(f"Table not found: {full_name!r}")
        storage = info.get("storage_location")
        if not isinstance(storage, str) or not storage:
            raise CatalogNotFoundError(
                f"Table {full_name!r} has no storage_location on soyuz-catalog.",
            )
        await check_privilege(uc_client, ctx.actor_email, ctx.is_admin, "table", full_name, SELECT)
        approved[full_name] = storage
    return approved


async def _enforce_modify_target(
    ctx: DispatchContext, target: str, *, must_exist: bool
) -> bool:
    """Enforce write privilege on *target* and report whether it exists.

    Mirrors :func:`pointlessql.api.pql_write_routes._check_write_target`
    so editor and Hermes-plugin write paths agree on the gate.

    Args:
        ctx: Dispatcher context.
        target: 3-part UC name.
        must_exist: When ``True``, raise if the target does not exist.

    Returns:
        ``True`` if the target already exists, ``False`` otherwise.

    Raises:
        ValidationError: When *target* is not 3-part.
        CatalogNotFoundError: When ``must_exist=True`` and target absent.
        AuthorizationError: When the caller lacks the required gate.
    """  # noqa: DOC502,DOC503
    parts = target.split(".")
    if len(parts) != 3:
        raise ValidationError(
            f"Internal error: expected 3-part name, got {target!r}.",
        )
    uc_client = get_uc_client(ctx.request)
    info = await uc_client.get_table(parts[0], parts[1], parts[2])
    if not info:
        if must_exist:
            raise CatalogNotFoundError(f"Table not found: {target!r}")
        # New-target path requires USE_SCHEMA on the parent so the
        # caller has permission to create children underneath.
        parent_schema = f"{parts[0]}.{parts[1]}"
        await check_privilege(
            uc_client, ctx.actor_email, ctx.is_admin, "schema", parent_schema, USE_SCHEMA
        )
        return False
    await check_privilege(uc_client, ctx.actor_email, ctx.is_admin, "table", target, MODIFY)
    return True


async def _start_editor_agent_run(
    ctx: DispatchContext, *, target_fqn: str
) -> str:
    """Create a one-shot ``agent_run`` row for an interactive editor write.

    Each editor write statement gets its own run with
    ``agent_id='sql-editor'``.  The PQL primitives (``write_table``,
    ``update``, ``delete``, ``merge``) detect the run id via the
    constructor kwarg threaded through ``_build_pql`` and emit
    ``agent_run_operations`` against it automatically.

    Args:
        ctx: Dispatcher context.
        target_fqn: The write target — recorded on
            ``tables_touched`` so the runs-list page surfaces it
            without joining ``agent_run_operations``.

    Returns:
        The new run's UUID string.
    """
    factory = ctx.request.app.state.session_factory
    run_id = str(uuid.uuid4())
    workspace_id = int(getattr(ctx.request.state, "workspace_id", 1))
    sql_sha = hashlib.sha256(ctx.sql.encode("utf-8")).hexdigest()
    started_at = datetime.now(UTC)

    def _insert() -> None:
        with factory() as session:
            row = AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal=ctx.actor_email or None,
                agent_id="sql-editor",
                notebook_path="<sql-editor>",
                source_snapshot_sha=sql_sha,
                status=STATUS_RUNNING,
                cost_est=None,
                tables_touched=json.dumps([target_fqn]),
                started_at=started_at,
                runtime_versions=json.dumps(
                    {"sql-editor": "63.0", "stmt_type": ctx.stype.value},
                    sort_keys=True,
                ),
            )
            session.add(row)
            session.commit()

    await asyncio.to_thread(_insert)
    return run_id


async def _finish_agent_run(
    ctx: DispatchContext,
    run_id: str,
    *,
    status: Literal["succeeded", "failed"],
    error: str | None = None,
) -> None:
    """Update *run_id* with terminal status + finish timestamp.

    Best-effort: a failed update path is logged but does not
    further raise — the underlying primitive's failure is the
    user-visible event.

    Args:
        ctx: Dispatcher context.
        run_id: UUID of the run to finalise.
        status: Terminal value, ``'succeeded'`` or ``'failed'``.
        error: Optional truncated error message recorded into
            ``denied_reason`` for failed runs.
    """
    factory = ctx.request.app.state.session_factory

    def _update() -> None:
        from sqlalchemy import select

        with factory() as session:
            row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if row is None:  # pragma: no cover — race we ignore
                return
            row.status = status
            row.finished_at = datetime.now(UTC)
            if status == "failed" and error:
                row.denied_reason = error[:1024]
            session.commit()

    try:
        await asyncio.to_thread(_update)
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("sql-editor agent_run finish update failed for %s", run_id)


async def _emit_ddl_op(
    ctx: DispatchContext,
    *,
    run_id: str,
    op_name_value: str,
    target_fqn: str,
    extras: dict[str, Any],
) -> None:
    """Record a single ``agent_run_operations`` row for a DDL action.

    DDL flows through the soyuz client (not a PQL primitive), so
    there is no :func:`operation_context` wrapper inside the
    catalog call.  This helper writes the op row directly so the
    audit trail has parity with DML.

    Args:
        ctx: Dispatcher context.
        run_id: Owning agent_run UUID.
        op_name_value: One of ``'drop_table'``, ``'create_schema'``,
            ``'drop_schema'``, ``'alter_table'``.  Must already be
            in the ``ck_agent_run_operations_op_name`` CHECK set
            (alembic ``ee3f6h8j0l2n``).
        target_fqn: 3-part FQN for tables, 2-part for schemas.
        extras: Free-form dict merged into ``params_json``.
    """
    from sqlalchemy import text

    factory = ctx.request.app.state.session_factory
    op_id = str(uuid.uuid4())
    started = datetime.now(UTC)
    params = {"target": target_fqn, **extras}

    def _insert() -> None:
        with factory() as session:
            session.execute(
                text(
                    "INSERT INTO agent_run_operations "
                    "(id, workspace_id, agent_run_id, op_name, params_json, "
                    "target_table, started_at, finished_at, status) "
                    "VALUES (:id, :ws, :run, :name, :params, :target, "
                    ":start, :finish, 'succeeded')",
                ),
                {
                    "id": op_id,
                    "ws": int(getattr(ctx.request.state, "workspace_id", 1)),
                    "run": run_id,
                    "name": op_name_value,
                    "params": json.dumps(params, sort_keys=True),
                    "target": target_fqn,
                    "start": started,
                    "finish": datetime.now(UTC),
                },
            )
            session.commit()

    try:
        await asyncio.to_thread(_insert)
    except Exception:  # noqa: BLE001 — best-effort
        logger.exception("sql-editor DDL op record failed for run=%s op=%s", run_id, op_name_value)


# ─── AST extraction shims ────────────────────────────────────────────


def _extract_source_select_sql(ast: Expression, stype: StmtType) -> str:
    """Return the source-SELECT SQL for INSERT-FROM-SELECT / CTAS.

    Args:
        ast: Parsed INSERT or CREATE TABLE AS SELECT expression.
        stype: Classification.

    Returns:
        The SELECT body rendered back to DuckDB-dialect SQL.

    Raises:
        SQLExecutionError: When the expected SELECT body is absent
            (sqlglot parse anomaly).
    """
    if stype is StmtType.INSERT_FROM_SELECT and isinstance(ast, exp.Insert):
        body = ast.expression
    elif stype is StmtType.CREATE_TABLE_AS and isinstance(ast, exp.Create):
        body = ast.expression
    else:
        body = None
    if body is None:
        raise SQLExecutionError("Could not extract source SELECT body from statement.")
    return body.sql(dialect="duckdb")


def _extract_update_args(ast: Expression) -> tuple[dict[str, str], str | None]:
    """Translate UPDATE AST into ``(set_clause, where)`` strings.

    Args:
        ast: Parsed UPDATE expression.

    Returns:
        ``(set_clause, where)`` ready for :meth:`PQL.update`.

    Raises:
        SQLExecutionError: When SET assignments cannot be rendered.
    """
    if not isinstance(ast, exp.Update):  # defensive
        raise SQLExecutionError("Internal error: _extract_update_args invoked on non-Update AST.")
    set_clause: dict[str, str] = {}
    for assignment in ast.args.get("expressions") or []:
        if not isinstance(assignment, exp.EQ):
            raise SQLExecutionError(
                "UPDATE SET clause must be a list of column = expression assignments.",
            )
        col = assignment.this
        rhs = assignment.expression
        if not isinstance(col, exp.Column) or rhs is None:
            raise SQLExecutionError(
                "UPDATE SET assignment must have shape `column = expression`.",
            )
        set_clause[col.name] = rhs.sql(dialect="duckdb")
    if not set_clause:
        raise SQLExecutionError("UPDATE statement has no SET assignments.")
    where_node = ast.args.get("where")
    where_sql: str | None = None
    if isinstance(where_node, exp.Where) and where_node.this is not None:
        where_sql = where_node.this.sql(dialect="duckdb")
    return set_clause, where_sql


def _extract_where_sql(ast: Expression) -> str | None:
    """Return the WHERE clause's SQL string, or ``None`` for no WHERE.

    Args:
        ast: Parsed UPDATE / DELETE expression.

    Returns:
        The WHERE clause rendered as SQL, or ``None`` when absent
        (full-table DELETE / unconditional UPDATE).
    """
    where_node = ast.args.get("where") if hasattr(ast, "args") else None
    if isinstance(where_node, exp.Where) and where_node.this is not None:
        return where_node.this.sql(dialect="duckdb")
    return None


def _int_or_none(value: Any) -> int | None:
    """Best-effort coerce *value* to ``int``, ``None`` on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_rows_affected(stats: dict[str, Any]) -> int | None:
    """Sum the merge-stats counters into a single rows-affected number.

    Args:
        stats: Dict from :meth:`PQL.merge`.

    Returns:
        Sum of inserted+updated+deleted counts, ``None`` when the
        stats dict has none of those keys.
    """
    keys = (
        "num_target_rows_inserted",
        "num_target_rows_updated",
        "num_target_rows_deleted",
        "rows_appended",
    )
    total = 0
    seen = False
    for key in keys:
        value = _int_or_none(stats.get(key))
        if value is not None:
            total += value
            seen = True
    return total if seen else None


__all__ = [
    "DispatchContext",
    "ExecutionResult",
    "PreparedSQL",
    "dispatch",
]
