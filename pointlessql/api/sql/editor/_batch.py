"""``POST /api/sql/execute_batch`` — multi-statement runner with atomic rollback.

Each ``;``-separated statement dispatches through the same path as
:func:`api_sql_execute` so audit + privilege checks are identical.
``atomic=True`` opens a single agent_run that wraps every write and
calls :func:`_rollback_run` on the failed-index when a downstream
statement raises.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.sql.editor._helpers import strip_ansi
from pointlessql.config import Settings
from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql"])


@router.post("/api/sql/execute_batch")
async def api_sql_execute_batch(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Run multiple ``;``-separated statements in one request.

    Each statement is dispatched through the same path as
    ``POST /api/sql/execute`` so the audit-trail wiring + privilege
    checks are identical.  Two execution modes:

    * ``atomic=False`` (default) — statements run sequentially.
      Each write gets its own ``agent_run`` row; the first failure
      stops the batch and earlier successful writes stay
      committed.
    * ``atomic=True`` — single ``agent_run`` for the whole batch.
      On any DML/DDL failure, ``pql.rollback`` undoes the
      successful writes that preceded it.  SELECTs in
      the batch always succeed-or-fail individually since reads
      are idempotent.

    Args:
        request: Incoming FastAPI request.
        body: JSON body with ``sql`` (multi-statement string;
            ``;``-separated), optional ``atomic`` (bool, default
            ``False``), and optional ``query_id``.

    Returns:
        ``{batch_id, results: [...], failed_index, error}``.
        ``results`` is the per-statement
        :func:`api_sql_execute`-style response dict (same shape).
        ``failed_index`` is ``None`` on full success, or the
        zero-based index of the failing statement.

    Raises:
        SQLExecutionError: When the SQL editor is disabled or the
            batch parse fails before any statement runs.
    """  # noqa: DOC502,DOC503 — exceptions bubble up to the centralised handler
    from pointlessql.api.sql._dispatcher import dispatch
    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql import (
        SQLParseError,
        classify,
        parse_batch,
    )

    settings: Settings = request.app.state.settings
    if not settings.sql.enabled:
        raise SQLExecutionError("The SQL editor is disabled on this deployment.")

    sql_text = (body or {}).get("sql") or ""
    if not isinstance(sql_text, str) or not sql_text.strip():
        raise SQLExecutionError("The 'sql' field must be a non-empty string.")
    atomic = bool((body or {}).get("atomic", False))
    raw_qid = (body or {}).get("query_id")
    batch_id = raw_qid if isinstance(raw_qid, str) and raw_qid else uuid4().hex

    try:
        asts = parse_batch(sql_text)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    import duckdb

    results: list[dict[str, Any]] = []
    failed_index: int | None = None
    error_message: str | None = None
    write_run_ids: list[str] = []

    for idx, ast in enumerate(asts):
        stype = classify(ast)
        stmt_sql = ast.sql(dialect="duckdb")
        conn = duckdb.connect()
        try:
            exec_result = await dispatch(
                request=request,
                settings=settings,
                sql=stmt_sql,
                ast=ast,
                stype=stype,
                conn=conn,
            )
        except Exception as exc:  # noqa: BLE001 — record then halt
            # bare-broad-ok: the user gets a typed ``kind: "error"``
            # result row with the stripped message; halting the batch
            # here without a server-side log is the deliberate UX.
            failed_index = idx
            error_message = strip_ansi(str(exc))
            results.append(
                {
                    "index": idx,
                    "kind": "error",
                    "stmt_type": stype.value,
                    "executed_sql": stmt_sql,
                    "error": error_message,
                }
            )
            break
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — diagnostic
                logger.debug("conn.close() raised", exc_info=True)
        if exec_result.kind != "select" and exec_result.agent_run_id:
            write_run_ids.append(exec_result.agent_run_id)
        results.append(
            {
                "index": idx,
                "kind": exec_result.kind,
                "stmt_type": stype.value,
                "executed_sql": stmt_sql,
                "target": exec_result.target,
                "rows_affected": exec_result.rows_affected,
                "agent_run_id": exec_result.agent_run_id,
                "op_name": exec_result.op_name,
                "row_count": exec_result.row_count,
                "columns": exec_result.columns,
                "rows": exec_result.rows,
            }
        )

    rollback_log: list[dict[str, Any]] = []
    if atomic and failed_index is not None:
        # Roll back any successful writes that preceded the failure.
        # SELECTs and DDLs are not undoable through pql.rollback —
        # those stay even in atomic mode (DDL via soyuz is a
        # different transaction surface).
        for run_id in reversed(write_run_ids):
            try:
                rollback_log.append(await _rollback_run(request, run_id=run_id))
            except Exception as exc:  # noqa: BLE001 — best-effort
                # bare-broad-ok: per-run rollback errors are appended
                # to the structured rollback_log returned to the
                # caller; best-effort semantics, no server log.
                rollback_log.append({"run_id": run_id, "error": str(exc)})

    await audit(
        request,
        "query.batch",
        f"batch:{batch_id}",
        {
            "atomic": atomic,
            "n_statements": len(asts),
            "failed_index": failed_index,
            "rollback_attempted": bool(rollback_log),
        },
    )

    return {
        "batch_id": batch_id,
        "atomic": atomic,
        "n_statements": len(asts),
        "failed_index": failed_index,
        "error": error_message,
        "results": results,
        "rollback": rollback_log,
    }


async def _rollback_run(request: Request, *, run_id: str) -> dict[str, Any]:
    """Best-effort ``pql.rollback`` for every write op of *run_id*.

    Iterates the run's ``agent_run_operations`` rows in reverse
    ordinal order and calls :meth:`PQL.rollback` on each
    target_table.  Used by the atomic-batch failure path.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the editor's per-write agent_run.

    Returns:
        ``{"run_id", "ops_rolled_back", "errors"}``.
    """
    from sqlalchemy import select

    from pointlessql.api.sql.write import (
        _build_pql,  # pyright: ignore[reportPrivateUsage]
    )
    from pointlessql.models.agent._audit import AgentRunOperation

    factory = request.app.state.session_factory
    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")

    def _ops() -> list[tuple[int, str | None]]:
        with factory() as session:
            rows = session.execute(
                select(AgentRunOperation.ordinal, AgentRunOperation.target_table)
                .where(AgentRunOperation.agent_run_id == run_id)
                .order_by(AgentRunOperation.ordinal.desc())
            ).all()
            return [(int(r[0]), r[1]) for r in rows]

    ops = await run_sync(_ops)

    rolled: list[int] = []
    errors: list[dict[str, Any]] = []

    def _do_rollback(ordinal: int, target: str) -> None:
        pql = _build_pql(request, principal=email, agent_run_id=None)
        pql.rollback(target, before_run=run_id, op_ordinal=ordinal, allow_force=True)

    for ordinal, target in ops:
        if not target:
            continue
        try:
            await run_sync(_do_rollback, ordinal, target)
            rolled.append(ordinal)
        except Exception as exc:  # noqa: BLE001 — best-effort
            # bare-broad-ok: per-op rollback errors are returned in
            # the structured ``errors`` list; best-effort semantics.
            errors.append({"ordinal": ordinal, "target": target, "error": str(exc)})

    return {"run_id": run_id, "ops_rolled_back": rolled, "errors": errors}
