"""``_run_statement`` — async executor for one SQL statement submission.

The route layer creates the ``sql_statements`` row, generates the
statement_id, and launches :func:`run_statement` as a background
task.  This module owns:

* Per-statement task registry (in-process dict keyed by statement_id)
  so the cancel route can both ``task.cancel()`` AND call
  ``conn.interrupt()`` on the DuckDB handle.
* Run wrapper: parse-classify → ensure SELECT → enforce_select_per_table
  → run_sql_sync → DBX envelope serialisation → persist + audit.
* Mapping of internal exceptions to DBX error codes.

Authorization fans out via the same ``enforce_select_per_table()``
helper the editor route uses, so soyuz-catalog grants apply
uniformly across both surfaces.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table
from pointlessql.api.sql._dispatcher._types import DispatchContext
from pointlessql.api.sql.editor._helpers import run_sql_sync
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogNotFoundError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.models import SqlStatement
from pointlessql.pql import SQLParseError, StmtType, parse_and_classify
from pointlessql.services import audit as audit_service
from pointlessql.services.sql_statements._envelope import (
    build_dbx_envelope,
    error_envelope,
    status_envelope,
)

logger = logging.getLogger(__name__)


@dataclass
class _RegisteredTask:
    """In-process handle linking statement_id → task + DuckDB conn.

    The cancel route needs both pointers: ``task.cancel()`` interrupts
    the coroutine boundary; ``conn.interrupt()`` interrupts the
    DuckDB execute call (which is uninterruptible from Python land
    once it has dispatched into the C engine).
    """

    task: asyncio.Task[Any]
    conn: Any = None


def _task_registry(app_state: Any) -> dict[str, _RegisteredTask]:
    """Return the in-process registry, creating it on first use.

    Lives on ``app.state.sql_statement_tasks`` so every worker in the
    same process shares one dict.  Multi-worker deployments don't
    share this; cancel relies on the request landing on the same
    worker that started the statement, which is the typical case for
    a sticky load balancer + short-running queries.

    Args:
        app_state: ``app.state`` of the running app.

    Returns:
        Mutable registry dict.
    """
    registry: dict[str, _RegisteredTask] | None = getattr(
        app_state, "sql_statement_tasks", None
    )
    if registry is None:
        registry = {}
        app_state.sql_statement_tasks = registry
    return registry


def register_statement_task(
    app_state: Any,
    statement_id: str,
    task: asyncio.Task[Any],
) -> None:
    """Insert a freshly-spawned executor task into the cancel registry."""
    _task_registry(app_state)[statement_id] = _RegisteredTask(task=task)


def unregister_statement_task(app_state: Any, statement_id: str) -> None:
    """Drop the task entry once execution finishes.  Idempotent."""
    _task_registry(app_state).pop(statement_id, None)


def _bind_conn(app_state: Any, statement_id: str, conn: Any) -> None:
    """Attach the live DuckDB connection so cancel can interrupt it."""
    entry = _task_registry(app_state).get(statement_id)
    if entry is not None:
        entry.conn = conn


def cancel_statement(app_state: Any, statement_id: str) -> bool:
    """Cancel an in-flight statement.  Best-effort; returns success flag.

    Sequence:

    1. Look up the registered task + conn.
    2. If a DuckDB conn is bound, call ``conn.interrupt()`` — this
       wakes ``run_sql_sync`` mid-execute with ``InterruptException``.
    3. Call ``task.cancel()`` so a coroutine awaiting at any other
       point exits via ``CancelledError``.

    The executor's exception handler maps both to CANCELED state.

    Args:
        app_state: ``app.state`` of the running app.
        statement_id: Statement to cancel.

    Returns:
        ``True`` if at least one cancellation primitive fired.
    """
    entry = _task_registry(app_state).get(statement_id)
    if entry is None:
        return False
    fired = False
    if entry.conn is not None:
        try:
            entry.conn.interrupt()
            fired = True
        except Exception:  # noqa: BLE001 — diagnostic only
            logger.debug("conn.interrupt() raised", exc_info=True)
    if not entry.task.done():
        entry.task.cancel()
        fired = True
    return fired


def fetch_statement(
    session_factory: sessionmaker[Session], statement_id: str
) -> SqlStatement | None:
    """Return the persisted row (detached) or ``None`` when missing."""
    with session_factory() as session:
        row = session.scalar(
            select(SqlStatement).where(SqlStatement.statement_id == statement_id)
        )
        if row is None:
            return None
        session.expunge(row)
        return row


def _persist_running(
    session_factory: sessionmaker[Session], statement_id: str
) -> None:
    """Flip the row to ``RUNNING`` + record ``started_at`` (best-effort)."""
    with session_factory() as session:
        session.execute(
            update(SqlStatement)
            .where(SqlStatement.statement_id == statement_id)
            .values(status="RUNNING", started_at=datetime.now(UTC))
        )
        session.commit()


def _persist_success(
    session_factory: sessionmaker[Session],
    statement_id: str,
    payload: bytes,
) -> None:
    """Persist a SUCCEEDED row + gzipped envelope.  Best-effort."""
    with session_factory() as session:
        session.execute(
            update(SqlStatement)
            .where(SqlStatement.statement_id == statement_id)
            .values(
                status="SUCCEEDED",
                result_payload=payload,
                completed_at=datetime.now(UTC),
            )
        )
        session.commit()


def _persist_failure(
    session_factory: sessionmaker[Session],
    statement_id: str,
    *,
    state: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    """Persist a FAILED / CANCELED row.  Best-effort."""
    with session_factory() as session:
        session.execute(
            update(SqlStatement)
            .where(SqlStatement.statement_id == statement_id)
            .values(
                status=state,
                error_code=error_code,
                error_message=(error_message or "")[:4096],
                completed_at=datetime.now(UTC),
            )
        )
        session.commit()


def _map_exception_to_dbx(exc: BaseException) -> tuple[str, str]:
    """Translate a known exception type to (error_code, message).

    Args:
        exc: The exception caught in the executor.

    Returns:
        ``(error_code, message)`` tuple suitable for DBX envelope.
    """
    if isinstance(exc, SQLParseError):
        return "SQL_PARSE_ERROR", str(exc)
    if isinstance(exc, AuthorizationError):
        return "PERMISSION_DENIED", str(exc)
    if isinstance(exc, CatalogNotFoundError):
        return "RESOURCE_NOT_FOUND", str(exc)
    if isinstance(exc, (ValidationError, ValueError)):
        return "INVALID_PARAMETER_VALUE", str(exc)
    if isinstance(exc, SQLExecutionError):
        return "SQL_PARSE_ERROR", str(exc)
    return "INTERNAL_ERROR", str(exc) or exc.__class__.__name__


async def run_statement(
    *,
    request: Any,
    statement_id: str,
    sql_text: str,
    row_limit: int,
    timeout_seconds: int,
    api_key_name: str,
    actor_email: str,
) -> dict[str, Any]:
    """Run one submitted statement end-to-end.

    Reads ``request.app.state`` for the settings + session factory +
    task registry.  Returns the DBX envelope to be either returned
    directly (sync) or used by the poll handler (after persist).

    Args:
        request: FastAPI request (need ``request.app.state`` for
            settings / session factory / UC client; also the
            ``DispatchContext`` for SELECT enforcement).
        statement_id: Public statement handle.
        sql_text: Already-qualified, already-bound SQL.
        row_limit: Effective row cap (already clamped).
        timeout_seconds: Per-execution DuckDB timeout.
        api_key_name: For audit attribution.
        actor_email: Effective principal (X-Principal override or
            API-key principal) for SELECT enforcement.

    Returns:
        DBX envelope dict (SUCCEEDED, FAILED, or CANCELED).

    Raises:
        SQLExecutionError: When parse / timeout / interrupt fails
            (caught by the terminal handler and persisted as FAILED).
        ValidationError: When a non-SELECT statement is submitted.
    """  # noqa: DOC502  — both are caught by the terminal handler
    import duckdb

    app_state = request.app.state
    settings = app_state.settings
    factory = app_state.session_factory
    conn: Any = None

    _persist_running(factory, statement_id)

    try:
        try:
            ast, stype = parse_and_classify(sql_text)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc

        if stype is not StmtType.SELECT:
            # v1 is read-only; everything non-SELECT is a hard reject
            # at parse time so downstream code never has to defend
            # against an unexpected branch.
            raise ValidationError(
                "The public SQL Statement API accepts SELECT only in v1; "
                "use the editor for DML/DDL."
            )

        conn = duckdb.connect()
        _bind_conn(app_state, statement_id, conn)

        # Reuse the editor's privilege-enforcement helper so soyuz
        # SELECT grants apply uniformly across both surfaces.
        from pointlessql.pql import prepare_sql

        prepared = prepare_sql(sql_text)
        ctx = DispatchContext(
            request=request,
            settings=settings,
            sql=sql_text,
            ast=ast,
            stype=stype,
            actor_email=actor_email,
            is_admin=False,
            conn=conn,
            max_rows=row_limit,
        )
        approved = await enforce_select_per_table(ctx, prepared.refs)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_sql_sync,
                    settings,
                    sql_text,
                    approved,
                    row_limit,
                    conn,
                    False,
                ),
                timeout=max(1, int(timeout_seconds)),
            )
        except asyncio.CancelledError:
            try:
                conn.interrupt()
            except Exception:  # noqa: BLE001 — diagnostic only
                logger.debug("conn.interrupt() after CancelledError raised", exc_info=True)
            _persist_failure(
                factory,
                statement_id,
                state="CANCELED",
                error_code=None,
                error_message="Statement cancelled by user.",
            )
            await _audit(
                request,
                statement_id,
                api_key_name,
                "canceled",
                detail={"reason": "cancel_requested"},
            )
            return status_envelope(statement_id=statement_id, state="CANCELED")
        except TimeoutError as exc:
            try:
                conn.interrupt()
            except Exception:  # noqa: BLE001 — diagnostic only
                logger.debug("conn.interrupt() after timeout raised", exc_info=True)
            raise SQLExecutionError(
                f"Statement exceeded {timeout_seconds}s execution timeout and was cancelled."
            ) from exc
        except duckdb.InterruptException as exc:
            raise SQLExecutionError("Statement interrupted before completion.") from exc

        envelope = build_dbx_envelope(statement_id=statement_id, result=result)
        payload = gzip.compress(json.dumps(envelope).encode("utf-8"))
        _persist_success(factory, statement_id, payload)
        await _audit(
            request,
            statement_id,
            api_key_name,
            "succeeded",
            detail={
                "row_count": result.row_count,
                "duration_ms": result.duration_ms,
                "truncated": result.truncated,
                "tables": result.referenced_tables,
            },
        )
        return envelope

    except Exception as exc:  # noqa: BLE001 — terminal catch maps every failure to DBX envelope
        error_code, message = _map_exception_to_dbx(exc)
        _persist_failure(
            factory,
            statement_id,
            state="FAILED",
            error_code=error_code,
            error_message=message,
        )
        await _audit(
            request,
            statement_id,
            api_key_name,
            "failed",
            detail={"error_code": error_code, "message": message[:500]},
        )
        return error_envelope(
            statement_id=statement_id, error_code=error_code, message=message
        )
    finally:
        unregister_statement_task(app_state, statement_id)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — diagnostic only
                logger.debug("conn.close() raised", exc_info=True)


async def _audit(
    request: Any,
    statement_id: str,
    api_key_name: str,
    outcome: str,
    *,
    detail: dict[str, Any],
) -> None:
    """Append an audit row for one statement lifecycle event."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return
    workspace_id = int(getattr(request.state, "workspace_id", 1) or 1)
    user_email = f"api_key:{api_key_name}"
    merged = {"api_key": api_key_name, "outcome": outcome, **detail}
    try:
        await asyncio.to_thread(
            audit_service.log_action,
            factory,
            0,
            user_email,
            f"sql.statement.{outcome}",
            f"statement:{statement_id}",
            merged,
            actor_role="system",
            client_ip=None,
            workspace_id=workspace_id,
        )
    except Exception:  # noqa: BLE001 — audit must never mask the response
        logger.exception("audit write failed for statement %s", statement_id)
