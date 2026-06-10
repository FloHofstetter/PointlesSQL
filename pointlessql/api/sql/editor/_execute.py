"""``POST /api/sql/execute`` — single-statement editor entry point.

The largest sub-route in the editor family because it owns the full
parse → enforce → dispatch → audit envelope plus the legacy EXPLAIN
shim for SELECT.  The dispatcher (:mod:`api.sql._dispatcher`) handles
every statement family below; this module wraps it with the request-
level lifecycle (live-query registry, timeout, history record, audit
log entry).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit, record_query_async
from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.sql.editor._helpers import (
    live_queries,
    run_sql_sync,
    short_sql_hash,
    strip_ansi,
)
from pointlessql.config import Settings
from pointlessql.services._executor import run_sync
from pointlessql.types import QueryStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql"])


@router.post("/api/sql/execute")
async def api_sql_execute(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Parse, enforce, execute a single SELECT against the UC lakehouse.

    Flow:

    1. Parse via :func:`~pointlessql.pql.sql_parser.prepare_sql` to
       extract the 3-part table references and a DuckDB-safe rewrite
       of the SQL.
    2. For every referenced table: fetch ``storage_location`` from
       soyuz-catalog and call ``check_privilege(SELECT)``.  Admin
       short-circuits per :mod:`pointlessql.services.authorization`.
    3. Dispatch :meth:`PQL.sql` via :func:`asyncio.to_thread` so the
       event loop keeps serving other requests during the DuckDB
       call.
    4. Audit the execution with the ``query.executed`` action string.

    Errors raised inside the parse / enforce / execute stages map to
    RFC 9457 problem+json via the centralised handler.  The enforce
    stage propagates :class:`AuthorizationError` (raised by
    :func:`check_privilege` when the user lacks ``SELECT`` on a
    referenced table) and :class:`CatalogNotFoundError` (when a
    referenced table is unknown to soyuz-catalog or has no
    ``storage_location``).

    Args:
        request: The incoming FastAPI request.  Needs the auth
            middleware's resolved user and ``request.app.state.settings``.
        body: JSON body with a single ``sql`` key.

    Returns:
        The serialised :class:`SQLResult` as a plain dict.

    Raises:
        SQLExecutionError: If the SQL editor is disabled, the SQL is
            malformed or out-of-scope, or DuckDB rejects the query
            at execution time.
        Exception: Any failure from the parse / enforce / dispatch
            stages is re-raised verbatim after a failed history row
            is recorded, then mapped to problem+json by the
            centralised handler.
    """
    import duckdb

    from pointlessql.api.sql._dispatcher import dispatch
    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql import (
        SQLParseError,
        StmtType,
        parse_and_classify,
    )

    settings: Settings = request.app.state.settings
    if not settings.sql.enabled:
        raise SQLExecutionError("The SQL editor is disabled on this deployment.")

    query = (body or {}).get("sql") or ""
    if not isinstance(query, str):
        raise SQLExecutionError("The 'sql' field must be a string.")

    # Client supplies an opaque query_id the cancel endpoint uses to
    # reach the live DuckDB conn.  Empty / non-str → generate one
    # server-side so old clients keep working.
    raw_qid = (body or {}).get("query_id")
    query_id = raw_qid if isinstance(raw_qid, str) and raw_qid else uuid4().hex

    # Optional EXPLAIN ANALYZE mode (SELECT-only).  The server
    # parses + enforces the raw SELECT as usual, then wraps the
    # final statement with ``EXPLAIN ANALYZE``.  Diagnostic runs
    # skip history recording + audit to keep the operator-facing
    # surfaces clean.
    explain = bool((body or {}).get("explain", False))

    started_at = datetime.now(UTC)
    cancelled = False
    timed_out = False
    conn: Any = None
    registry = live_queries(request)
    try:
        try:
            ast, stype = parse_and_classify(query)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc

        if explain and stype is not StmtType.SELECT:
            raise SQLExecutionError(
                "EXPLAIN is only supported for SELECT statements.",
            )

        # Open a DuckDB connection for SELECT (cancellable) and for
        # write paths that materialise a source SELECT
        # (INSERT-FROM-SELECT, CTAS, MERGE).  UPDATE / DELETE /
        # DROP / CREATE SCHEMA do not need DuckDB but the conn is
        # cheap to open and the cancel registry path is preserved.
        conn = duckdb.connect()
        registry[query_id] = conn
        timeout_s = max(1, int(settings.sql.query_timeout_seconds))

        if stype is StmtType.SELECT and explain:
            # Legacy EXPLAIN path stays inline — feeds the
            # pre-existing JSON-plan renderer below.
            from pointlessql.api.sql._dispatcher import DispatchContext
            from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table
            from pointlessql.pql import prepare_sql

            prepared = prepare_sql(query)
            user = get_user(request)
            ctx = DispatchContext(
                request=request,
                settings=settings,
                sql=query,
                ast=ast,
                stype=stype,
                actor_email=effective_principal(request) or user.get("email", ""),
                is_admin=bool(user.get("is_admin", False)),
                conn=conn,
                max_rows=settings.sql.max_rows,
            )
            approved = await enforce_select_per_table(ctx, prepared.refs)
            try:
                result = await asyncio.wait_for(
                    run_sync(
                        run_sql_sync,
                        settings,
                        query,
                        approved,
                        settings.sql.max_rows,
                        conn,
                        True,  # explain
                    ),
                    timeout=timeout_s,
                )
            except TimeoutError:
                timed_out = True
                try:
                    conn.interrupt()
                except Exception:  # noqa: BLE001 — diagnostic only
                    logger.debug("conn.interrupt() after timeout raised", exc_info=True)
                raise SQLExecutionError(
                    f"Query exceeded {timeout_s}s timeout and was cancelled.",
                ) from None
            except duckdb.InterruptException as exc:
                cancelled = True
                raise SQLExecutionError("Query cancelled by user.") from exc

            return serialize_explain(query_id, query, result)

        try:
            exec_result = await asyncio.wait_for(
                dispatch(
                    request=request,
                    settings=settings,
                    sql=query,
                    ast=ast,
                    stype=stype,
                    conn=conn,
                ),
                timeout=timeout_s,
            )
        except SQLParseError as exc:
            # Late parse failures (e.g. _rewrite_select rejecting a
            # 2-part table name inside a SELECT branch) bubble up as
            # SQLExecutionError so the route's RFC 9457 envelope
            # carries the right code.
            raise SQLExecutionError(str(exc)) from exc
        except TimeoutError:
            timed_out = True
            try:
                conn.interrupt()
            except Exception:  # noqa: BLE001 — diagnostic only
                logger.debug("conn.interrupt() after timeout raised", exc_info=True)
            raise SQLExecutionError(
                f"Query exceeded {timeout_s}s timeout and was cancelled.",
            ) from None
        except duckdb.InterruptException as exc:
            cancelled = True
            raise SQLExecutionError("Query cancelled by user.") from exc
    except Exception as exc:
        # Failure path: record a history row so the user sees the
        # attempt in /queries even on error.  EXPLAIN runs skip
        # history (diagnostic only).
        finished_at = datetime.now(UTC)
        status = QueryStatus.CANCELLED if (cancelled or timed_out) else QueryStatus.FAILED
        if not explain:
            await record_query_async(
                request,
                sql_text=query,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                row_count=None,
                duration_ms=None,
                referenced_tables=[],
                error_message=strip_ansi(str(exc)),
            )
        raise
    finally:
        registry.pop(query_id, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — diagnostic
                logger.debug("conn.close() raised", exc_info=True)

    finished_at = datetime.now(UTC)
    history_id: int | None = None
    if exec_result.kind == "select":
        history_id = await record_query_async(
            request,
            sql_text=query,
            started_at=started_at,
            finished_at=finished_at,
            status=QueryStatus.SUCCEEDED,
            row_count=exec_result.row_count,
            duration_ms=exec_result.duration_ms,
            referenced_tables=exec_result.referenced_tables,
        )
        await audit(
            request,
            "query.executed",
            f"query:{short_sql_hash(query)}",
            {
                "row_count": exec_result.row_count,
                "duration_ms": exec_result.duration_ms,
                "tables": exec_result.referenced_tables,
                "truncated": exec_result.truncated,
            },
        )
        return {
            "query_id": query_id,
            "history_id": history_id,
            "is_explain": False,
            "explain_text": None,
            "explain_plan": None,
            "kind": "select",
            "columns": exec_result.columns,
            "rows": exec_result.rows,
            "row_count": exec_result.row_count,
            "truncated": exec_result.truncated,
            "duration_ms": exec_result.duration_ms,
            "executed_sql": exec_result.executed_sql,
            "referenced_tables": exec_result.referenced_tables,
        }

    # Write path (DML / DDL).  ``query_history`` records the SQL +
    # the originating ``agent_run_id`` so /runs/<id> can surface
    # the editor-authored statement.
    history_id = await record_query_async(
        request,
        sql_text=query,
        started_at=started_at,
        finished_at=finished_at,
        status=QueryStatus.SUCCEEDED,
        row_count=exec_result.rows_affected,
        duration_ms=None,
        referenced_tables=exec_result.referenced_tables
        or ([exec_result.target] if exec_result.target else []),
        agent_run_id=exec_result.agent_run_id,
        read_kind="sql_dml" if exec_result.kind == "dml" else "sql_ddl",
    )
    await audit(
        request,
        f"query.{exec_result.kind}",
        f"query:{short_sql_hash(query)}",
        {
            "stmt_type": stype.value,
            "target": exec_result.target,
            "rows_affected": exec_result.rows_affected,
            "agent_run_id": exec_result.agent_run_id,
        },
    )
    return {
        "query_id": query_id,
        "history_id": history_id,
        "is_explain": False,
        "explain_text": None,
        "explain_plan": None,
        "kind": exec_result.kind,
        "stmt_type": stype.value,
        "target": exec_result.target,
        "rows_affected": exec_result.rows_affected,
        "agent_run_id": exec_result.agent_run_id,
        "op_name": exec_result.op_name,
        "stats": exec_result.stats,
        "executed_sql": exec_result.executed_sql,
        "referenced_tables": exec_result.referenced_tables,
    }


def serialize_explain(query_id: str, sql_text: str, result: Any) -> dict[str, Any]:
    """Build the EXPLAIN-mode response dict (legacy SELECT-only path).

    Args:
        query_id: Client-supplied query ID.
        sql_text: Raw SQL submitted (unused in the response but
            kept for future parity with the write path).
        result: A :class:`SQLResult` from :func:`run_sql_sync`
            with EXPLAIN flag set.

    Returns:
        The historical EXPLAIN response dict.
    """
    del sql_text  # no SQL hash needed for diagnostic explain path
    explain_text: str | None = None
    explain_plan: dict[str, Any] | None = None
    plan_text: str | None = None
    for row in result.rows:
        for cell in row:
            if isinstance(cell, str) and cell.lstrip().startswith(("{", "[")):
                plan_text = cell
                break
        if plan_text is not None:
            break
    if plan_text is not None:
        try:
            parsed = json.loads(plan_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            explain_plan = parsed
            explain_text = json.dumps(parsed, indent=2)
        else:
            explain_text = plan_text
    else:
        lines: list[str] = []
        for row in result.rows:
            lines.append("\t".join("" if cell is None else str(cell) for cell in row))
        explain_text = "\n".join(lines)

    return {
        "query_id": query_id,
        "history_id": None,
        "is_explain": True,
        "explain_text": explain_text,
        "explain_plan": explain_plan,
        "kind": "select",
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
        "executed_sql": result.executed_sql,
        "referenced_tables": result.referenced_tables,
    }
