"""Dispatch a single SQL statement to its typed primitive.

The SQL editor's ``POST /api/sql/execute`` route is an
AST-classifying **dispatcher** that routes each statement family
to its correct primitive:

* ``SELECT`` / ``WITH ... SELECT`` → DuckDB rewriter (today's path).
* ``INSERT INTO ... SELECT`` → :meth:`PQL.write_table(mode='append')`.
* ``CREATE TABLE ... AS SELECT`` → :meth:`PQL.write_table(mode='overwrite')`.
* ``UPDATE`` → :meth:`PQL.update`.
* ``DELETE`` → :meth:`PQL.delete`.
* ``MERGE`` → :func:`translate_merge_ast` → :meth:`PQL.merge`.
* ``DROP TABLE`` → ``soyuz.delete_table``.
* ``CREATE/DROP SCHEMA`` → ``soyuz.create_schema`` / ``soyuz.delete_schema``.
* ``ALTER TABLE`` → currently rejected with a structured "use the
  table-detail UI" error (deferred — needs cross-repo soyuz
  ``update_table`` route).

Audit semantics:

* SELECT keeps today's behaviour — no agent_run row is created.
  Only ``query_history`` records the read.
* Every write statement opens a one-shot ``agent_run`` with
  ``agent_id='sql-editor'`` BEFORE invoking the primitive.  The
  primitives (``write_table`` / ``update`` / ``delete`` / etc.)
  emit ``agent_run_operations`` against that run id automatically
  via :func:`pointlessql.services.agent_runs.operation_context`.
* ``query_history.agent_run_id`` is populated for write statements
  so ``/runs/<id>`` can surface the originating SQL.

Privilege model mirrors the existing ``/api/pql/*`` write routes:

* SELECT path: per-table ``SELECT``.
* INSERT / CTAS / UPDATE / DELETE / MERGE: ``SELECT`` on source
  refs + ``MODIFY`` (or ``USE_SCHEMA`` for new-target CTAS) on
  target.
* DROP TABLE: ``MODIFY`` on target.
* CREATE/DROP SCHEMA: caller must be admin (matches the soyuz
  facade gates).

* :mod:`_types`         — ``DispatchContext`` + ``ExecutionResult``.
* :mod:`_privilege`     — per-table SELECT, per-target MODIFY.
* :mod:`_agent_run`     — editor agent_run lifecycle + DDL op emit.
* :mod:`_ast_extract`   — sqlglot → primitive-args translators.
* :mod:`_select`        — SELECT branch (isolated to break the
                          editor↔dispatcher import cycle).
* :mod:`_dml`           — INSERT/CTAS, UPDATE, DELETE, MERGE branches.
* :mod:`_ddl`           — DROP TABLE, CREATE/DROP SCHEMA branches.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlglot.expressions.core import Expression

from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.sql._dispatcher._ddl import (
    execute_create_schema,
    execute_drop_schema,
    execute_drop_table,
)
from pointlessql.api.sql._dispatcher._dml import (
    execute_delete,
    execute_insert,
    execute_merge,
    execute_update,
)
from pointlessql.api.sql._dispatcher._select import execute_select
from pointlessql.api.sql._dispatcher._types import DispatchContext, ExecutionResult
from pointlessql.config import Settings
from pointlessql.exceptions import SQLExecutionError
from pointlessql.pql import PreparedSQL, StmtType

__all__ = [
    "DispatchContext",
    "ExecutionResult",
    "PreparedSQL",
    "dispatch",
]


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
    :func:`pointlessql.api.sql.editor.api_sql_execute`.  Each
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
        return await execute_select(ctx)
    if stype is StmtType.INSERT_FROM_SELECT:
        return await execute_insert(ctx, mode="append")
    if stype is StmtType.CREATE_TABLE_AS:
        return await execute_insert(ctx, mode="overwrite", create_if_missing=True)
    if stype is StmtType.UPDATE:
        return await execute_update(ctx)
    if stype is StmtType.DELETE:
        return await execute_delete(ctx)
    if stype is StmtType.MERGE:
        return await execute_merge(ctx)
    if stype is StmtType.DROP_TABLE:
        return await execute_drop_table(ctx)
    if stype is StmtType.CREATE_SCHEMA:
        return await execute_create_schema(ctx)
    if stype is StmtType.DROP_SCHEMA:
        return await execute_drop_schema(ctx)
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
