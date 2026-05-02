"""SQL editor routes — execute, cancel, download, and the editor page.

Owns the four endpoints that back the SQL editor + the HTML page
that loads it:

* ``POST /api/sql/execute`` — parse → enforce → DuckDB → audit
  pipeline for a single SELECT.
* ``POST /api/sql/execute/{query_id}/cancel`` — call
  ``conn.interrupt()`` on the live DuckDB handle the execute route
  parked in the per-app live-queries registry.
* ``GET  /api/sql/execute/{history_id}/download`` — re-run a
  previously-recorded query (re-enforced!) and stream the result
  as CSV or Parquet.
* ``GET  /sql`` — the Jinja2 page.

Authorization model: every referenced 3-part table goes through
``check_privilege(SELECT)`` on every execute *and* every download —
a stale history row is not a bypass.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit, record_query_async
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def short_sql_hash(sql: str) -> str:
    """Return a short deterministic digest of *sql* for audit-log targets.

    The audit-log ``target`` field is a single human-readable identifier
    (``catalog:foo``, ``query:abc123``…); a full SQL string would blow
    past the reasonable column width.  A 12-char truncated SHA-256 is
    enough to correlate with the corresponding ``query_history`` row
    and to tell apart identical-looking queries.

    Args:
        sql: The SQL string to hash.

    Returns:
        A 12-character hexadecimal digest.
    """
    import hashlib

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def run_sql_sync(
    settings: Settings,
    query: str,
    approved_tables: dict[str, str],
    max_rows: int,
    conn: Any = None,
    explain: bool = False,
) -> Any:
    """Execute *query* in the sync :class:`PQL` SQL bridge.

    Wrapped in a thin module-level helper so the FastAPI route can
    dispatch it via :func:`asyncio.to_thread` without capturing the
    PQL import at request time.  Any :class:`SQLExecutionError` or
    :class:`ValidationError` raised inside propagates unchanged — the
    centralised error handler turns them into RFC 9457 responses.

    Args:
        settings: Application settings (unused by :meth:`PQL.sql` at
            present but threaded through so future engine selection
            can read it without signature churn).
        query: The user-entered SQL.
        approved_tables: Full-name → storage-location map that the
            route already enforced ``SELECT`` on.
        max_rows: Row cap applied after execution.
        conn: Optional pre-created DuckDB connection so the route
            can hold the handle for cancel / timeout interrupt.
        explain: When ``True``, prepend ``EXPLAIN ANALYZE`` to the
            rewritten SQL so the caller gets the physical plan
            instead of the actual rows.

    Returns:
        A :class:`pointlessql.pql.pql.SQLResult` dataclass.
    """
    from pointlessql.pql.pql import PQL

    del settings  # reserved for future engine selection
    return PQL.sql(
        query,
        approved_tables=approved_tables,
        max_rows=max_rows,
        conn=conn,
        explain=explain,
    )


def live_queries(request: Request) -> dict[str, Any]:
    """Return the per-app live-queries registry, creating it on first use.

    Stored on ``app.state._live_queries`` so every worker in the same
    process shares one dict.  Keys are client-supplied query IDs
    (UUIDs); values are live :class:`duckdb.DuckDBPyConnection`
    handles.  The execute route registers on entry and pops on exit;
    the cancel route calls ``.interrupt()`` on whatever it finds.
    Multi-worker deployments don't share this map across processes —
    cancel currently relies on single-worker correctness; multi-worker
    cancel is a future concern.

    Args:
        request: The incoming request (for ``request.app.state``).

    Returns:
        The mutable registry dict (live for the app's lifetime).
    """
    registry: dict[str, Any] | None = getattr(
        request.app.state,
        "_live_queries",
        None,
    )
    if registry is None:
        registry = {}
        request.app.state._live_queries = registry
    return registry


def run_sql_export_sync(
    settings: Settings,
    query: str,
    approved_tables: dict[str, str],
    max_rows: int,
) -> Any:
    """Execute *query* and return the full pyarrow Table.

    Export needs the arrow buffer, not a JSON-flattened dict.  We
    run via a fresh connection (no cancel registry; the export
    request is expected to be brief since it re-runs a previously
    successful query from history).  Row-cap applies so a huge
    download cannot be coerced by editing ``?format=``.

    Args:
        settings: Reserved for future engine switches.
        query: The SQL to re-run.
        approved_tables: Enforcement-gated mapping.
        max_rows: Row cap.

    Returns:
        A :class:`pyarrow.Table` already sliced to *max_rows*.

    Raises:
        SQLExecutionError: If DuckDB rejects the query at execution
            time (column not found, type mismatch, …).
    """
    import duckdb

    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql.engine import register_delta_view
    from pointlessql.pql.sql_parser import prepare_sql

    del settings
    prepared = prepare_sql(query)
    conn = duckdb.connect()
    try:
        for ref in prepared.refs:
            register_delta_view(conn, ref, approved_tables[ref])
        try:
            arrow_table = conn.execute(prepared.rewritten_sql).to_arrow_table()
        except duckdb.Error as exc:
            raise SQLExecutionError(str(exc)) from exc
    finally:
        conn.close()
    if arrow_table.num_rows > max_rows:
        arrow_table = arrow_table.slice(0, max_rows)
    return arrow_table


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
    RFC 9457 problem+json via the centralised handler.

    Args:
        request: The incoming FastAPI request.  Needs ``request.state.user``
            (auth middleware) and ``request.app.state.settings``.
        body: JSON body with a single ``sql`` key.

    Returns:
        The serialised :class:`SQLResult` as a plain dict.

    Raises:
        SQLExecutionError: If the SQL editor is disabled, the SQL is
            malformed or out-of-scope, or DuckDB rejects the query
            at execution time.
        AuthorizationError: If the user lacks ``SELECT`` on any
            referenced table (raised by :func:`check_privilege`).
        CatalogNotFoundError: If a referenced table is unknown to
            soyuz-catalog or has no ``storage_location``.
    """  # noqa: DOC502,DOC503 — AuthorizationError is raised inside check_privilege
    import duckdb

    from pointlessql.exceptions import CatalogNotFoundError, SQLExecutionError
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

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

    # Optional EXPLAIN ANALYZE mode.  The server parses + enforces
    # the raw SELECT as usual, then wraps the final statement with
    # ``EXPLAIN ANALYZE``.  Diagnostic runs skip history recording
    # + audit to keep the operator-facing surfaces clean.
    explain = bool((body or {}).get("explain", False))

    started_at = datetime.now(UTC)
    parsed_refs: list[str] = []
    cancelled = False
    timed_out = False
    conn: Any = None
    registry = live_queries(request)
    try:
        try:
            prepared = prepare_sql(query)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc
        parsed_refs = list(prepared.refs)

        client = get_uc_client(request)
        user = get_user(request)
        email = effective_principal(request) or user.get("email", "")
        is_admin = user.get("is_admin", False)

        approved: dict[str, str] = {}
        for full_name in prepared.refs:
            parts = full_name.split(".")
            if len(parts) != 3:
                raise SQLExecutionError(
                    f"Internal error: expected 3-part name, got {full_name!r}.",
                )
            table_info = await client.get_table(parts[0], parts[1], parts[2])
            if not table_info:
                raise CatalogNotFoundError(f"Table not found: {full_name!r}")
            storage_location = table_info.get("storage_location")
            if not isinstance(storage_location, str) or not storage_location:
                raise CatalogNotFoundError(
                    f"Table {full_name!r} has no storage_location on soyuz-catalog.",
                )
            await check_privilege(client, email, is_admin, "table", full_name, SELECT)
            approved[full_name] = storage_location

        # Open the connection here and hand it to the thread so the
        # cancel endpoint can reach ``.interrupt()`` via the
        # live-queries registry.
        conn = duckdb.connect()
        registry[query_id] = conn
        timeout_s = max(1, int(settings.sql.query_timeout_seconds))
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_sql_sync,
                    settings,
                    query,
                    approved,
                    settings.sql.max_rows,
                    conn,
                    explain,
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            # Signal DuckDB to abort the running statement; the
            # worker thread observes the interrupt and raises.  We
            # then surface the timeout as a ``cancelled`` history
            # row (not ``failed``) because the query may have been
            # valid — just slow.
            timed_out = True
            try:
                conn.interrupt()
            except Exception as exc:  # noqa: BLE001 — diagnostic only
                logger.debug("conn.interrupt() after timeout raised: %s", exc)
            raise SQLExecutionError(
                f"Query exceeded {timeout_s}s timeout and was cancelled.",
            ) from None
        except duckdb.InterruptException as exc:
            # Cancelled by the /cancel endpoint.
            cancelled = True
            raise SQLExecutionError("Query cancelled by user.") from exc
    except Exception as exc:
        # Failure path: record history row before the centralised
        # error handler renders the response.  EXPLAIN runs skip
        # history (diagnostic only).  Parse failures have empty
        # ``parsed_refs``; enforcement failures carry the
        # references extracted before the check raised.
        finished_at = datetime.now(UTC)
        status = "cancelled" if (cancelled or timed_out) else "failed"
        if not explain:
            await record_query_async(
                request,
                sql_text=query,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                row_count=None,
                duration_ms=None,
                referenced_tables=parsed_refs,
                error_message=str(exc),
            )
        raise
    finally:
        registry.pop(query_id, None)
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:  # noqa: BLE001 — diagnostic
                logger.debug("conn.close() raised: %s", exc)

    finished_at = datetime.now(UTC)
    history_id: int | None = None
    if not explain:
        history_id = await record_query_async(
            request,
            sql_text=query,
            started_at=started_at,
            finished_at=finished_at,
            status="succeeded",
            row_count=result.row_count,
            duration_ms=result.duration_ms,
            referenced_tables=result.referenced_tables,
        )
        await audit(
            request,
            "query.executed",
            f"query:{short_sql_hash(query)}",
            {
                "row_count": result.row_count,
                "duration_ms": result.duration_ms,
                "tables": result.referenced_tables,
                "truncated": result.truncated,
            },
        )

    explain_text: str | None = None
    explain_plan: dict[str, Any] | None = None
    if explain:
        # Sprint 23 — DuckDB is now in JSON profiling mode (set by
        # ``_sql.py`` before the EXPLAIN ANALYZE call), so the
        # result-set carries a single JSON blob instead of the
        # legacy ASCII tree.  Find the JSON cell, parse it for the
        # frontend's structured renderer, AND keep a pretty-printed
        # text fallback so older clients / cURL still see something
        # readable.
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
            # Defensive fallback: pragma may have failed; flatten
            # whatever DuckDB returned into a tab-joined blob.
            lines: list[str] = []
            for row in result.rows:
                lines.append("\t".join("" if cell is None else str(cell) for cell in row))
            explain_text = "\n".join(lines)

    return {
        "query_id": query_id,
        "history_id": history_id,
        "is_explain": explain,
        "explain_text": explain_text,
        "explain_plan": explain_plan,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
        "executed_sql": result.executed_sql,
        "referenced_tables": result.referenced_tables,
    }


@router.post("/api/sql/execute/{query_id}/cancel", status_code=204)
async def api_sql_cancel(request: Request, query_id: str) -> Response:
    """Interrupt a running query by its client-supplied ``query_id``.

    The execute route registers each live :class:`duckdb.DuckDBPyConnection`
    in a per-app dict keyed by ``query_id``; this endpoint looks it
    up and calls ``.interrupt()``, which signals DuckDB to abort
    the currently-executing statement.  The worker thread observes
    an :class:`duckdb.InterruptException`, which the execute route
    maps to a ``cancelled`` history row.

    Cancelling an unknown / already-completed ``query_id`` is a
    no-op (204) — the client may race the execute response and we
    want idempotence.  Audit tag ``query.cancelled`` records the
    intent either way so operators can see cancel attempts.

    Args:
        request: Incoming FastAPI request.
        query_id: The client-supplied identifier from the execute body.

    Returns:
        An empty 204 response.
    """
    registry = live_queries(request)
    conn = registry.get(query_id)
    if conn is not None:
        try:
            conn.interrupt()
        except Exception as exc:  # noqa: BLE001 — diagnostic only
            logger.warning("conn.interrupt() raised on cancel: %s", exc)
    await audit(request, "query.cancelled", f"query_id:{query_id}", None)
    return Response(status_code=204)


@router.get("/api/sql/execute/{history_id}/download")
async def api_sql_download(
    request: Request,
    history_id: int,
    format: Literal["csv", "parquet"] = "csv",
) -> Response:
    """Stream a historical query's result as CSV or Parquet.

    The flow mirrors ``POST /api/sql/execute`` but reads the SQL
    from the ``query_history`` row instead of the request body:

    1. Fetch the history row; require the caller to be the owner
       or an admin.  Any other user sees a 404 so they cannot
       probe for history IDs.
    2. Re-run enforcement per referenced table — a history row is
       **not** a bypass.  Grants can be revoked after the original
       run; we must not leak data via an old history ID.
    3. Re-execute the SQL against DuckDB.  Stream the resulting
       Arrow table out as CSV (generator over rows) or Parquet
       (full write to an in-memory buffer, single response).

    Args:
        request: The incoming request.
        history_id: Primary key of the :class:`QueryHistory` row.
        format: ``"csv"`` (default) or ``"parquet"``.

    Returns:
        A :class:`StreamingResponse` (CSV) or :class:`Response`
        (Parquet) with a filename-stamped ``Content-Disposition``.

    Raises:
        CatalogNotFoundError: If the history row is missing, the
            caller cannot see it, or a referenced table is no
            longer registered in soyuz-catalog.
        SQLExecutionError: If re-parse or re-execution fails.
        AuthorizationError: If the caller lost ``SELECT`` on a
            referenced table since the original run.
    """  # noqa: DOC502,DOC503 — raised by helpers below + check_privilege
    import csv
    import io

    from fastapi.responses import StreamingResponse

    from pointlessql.exceptions import CatalogNotFoundError, SQLExecutionError
    from pointlessql.models import QueryHistory
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    settings: Settings = request.app.state.settings
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"History row {history_id!r} not found.")

    user = get_user(request)
    is_admin = user.get("is_admin", False)

    def _fetch_row() -> QueryHistory | None:
        from sqlalchemy import select as _select

        with factory() as session:
            return session.scalar(_select(QueryHistory).where(QueryHistory.id == history_id))

    row = await asyncio.to_thread(_fetch_row)
    if row is None or (not is_admin and row.user_id != user["id"]):
        raise CatalogNotFoundError(f"History row {history_id!r} not found.")

    try:
        prepared = prepare_sql(row.sql_text)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    client = get_uc_client(request)
    email = effective_principal(request) or user.get("email", "")
    approved: dict[str, str] = {}
    for full_name in prepared.refs:
        parts = full_name.split(".")
        table_info = await client.get_table(parts[0], parts[1], parts[2])
        if not table_info:
            raise CatalogNotFoundError(f"Table not found: {full_name!r}")
        storage_location = table_info.get("storage_location")
        if not isinstance(storage_location, str) or not storage_location:
            raise CatalogNotFoundError(
                f"Table {full_name!r} has no storage_location on soyuz-catalog.",
            )
        await check_privilege(client, email, is_admin, "table", full_name, SELECT)
        approved[full_name] = storage_location

    arrow_table = await asyncio.to_thread(
        run_sql_export_sync,
        settings,
        row.sql_text,
        approved,
        settings.sql.max_rows,
    )

    fmt = format.lower()
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"query-{history_id}-{ts}.{fmt}"
    await audit(
        request,
        "query.exported",
        f"history:{history_id}",
        {"format": fmt, "row_count": arrow_table.num_rows},
    )

    if fmt == "parquet":
        import pyarrow.parquet as pq

        sink = io.BytesIO()
        pq.write_table(arrow_table, sink)
        body = sink.getvalue()
        return Response(
            content=body,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # CSV default — stream row-by-row so large results don't
    # materialise in memory twice.
    def _csv_stream() -> Any:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(arrow_table.column_names)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for batch in arrow_table.to_batches(max_chunksize=1000):
            for rec in batch.to_pylist():
                writer.writerow([rec.get(c) for c in arrow_table.column_names])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(
        _csv_stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/sql/explain")
async def api_sql_explain(request: Request, sql: str = "") -> dict[str, Any]:
    """Return a DuckDB EXPLAIN plan + heuristic cost for *sql*.

    Cost gate.  Mirrors the parse + UC-SELECT-enforce front-half of
    :func:`api_sql_execute` so the caller cannot EXPLAIN a query
    whose tables they don't have permission to read — that would
    leak schema information through the plan even without row
    materialisation.

    Above ``settings.sql.cost_gate_threshold_rows`` the response
    flips ``needs_approval`` to ``True``.  No enforcement happens
    here — the agent or run-detail UI decides what to do with the
    flag.

    Args:
        request: Incoming FastAPI request.  Reads
            ``request.state.user`` (auth middleware) and
            ``request.app.state.settings``.
        sql: The SELECT statement to analyse (passed as a query-
            string parameter for convenient ``curl`` usage).

    Returns:
        Plain dict with ``plan`` (the parsed JSON tree DuckDB
        emitted), ``cost`` (heuristic dict with
        ``max_cardinality`` / ``join_depth`` / ``cost`` /
        ``explanation``), ``needs_approval`` (bool against the
        configured threshold), ``threshold`` (the threshold echoed
        for client reasoning), and ``referenced_tables`` (the
        enforcement list).

    Raises:
        SQLExecutionError: SQL editor disabled, malformed SQL, or
            DuckDB rejected the EXPLAIN.
        AuthorizationError: User lacks ``SELECT`` on a referenced
            table (raised by :func:`check_privilege`).
        CatalogNotFoundError: Referenced table unknown to
            soyuz-catalog or has no ``storage_location``.
    """  # noqa: DOC502,DOC503 — AuthorizationError is raised inside check_privilege
    from pointlessql.exceptions import CatalogNotFoundError, SQLExecutionError
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql
    from pointlessql.services.sql import run_explain

    settings: Settings = request.app.state.settings
    if not settings.sql.enabled:
        raise SQLExecutionError("The SQL editor is disabled on this deployment.")

    query = (sql or "").strip()
    if not query:
        raise SQLExecutionError("The 'sql' query parameter must be a non-empty string.")

    try:
        prepared = prepare_sql(query)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc

    client = get_uc_client(request)
    user = get_user(request)
    email = effective_principal(request) or user.get("email", "")
    is_admin = user.get("is_admin", False)

    approved: dict[str, str] = {}
    for full_name in prepared.refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            raise SQLExecutionError(
                f"Internal error: expected 3-part name, got {full_name!r}.",
            )
        table_info = await client.get_table(parts[0], parts[1], parts[2])
        if not table_info:
            raise CatalogNotFoundError(f"Table not found: {full_name!r}")
        storage_location = table_info.get("storage_location")
        if not isinstance(storage_location, str) or not storage_location:
            raise CatalogNotFoundError(
                f"Table {full_name!r} has no storage_location on soyuz-catalog.",
            )
        await check_privilege(client, email, is_admin, "table", full_name, SELECT)
        approved[full_name] = storage_location

    try:
        result = await asyncio.to_thread(run_explain, prepared.rewritten_sql, approved)
    except ValueError as exc:
        raise SQLExecutionError(str(exc)) from exc

    threshold = max(0, int(settings.sql.cost_gate_threshold_rows))
    needs_approval = threshold > 0 and result.cost.cost > threshold

    await audit(
        request,
        "query.explained",
        f"query:{short_sql_hash(query)}",
        {
            "tables": result.referenced_tables,
            "cost": result.cost.cost,
            "needs_approval": needs_approval,
        },
    )
    response: dict[str, Any] = {
        "plan": result.plan,
        "cost": {
            "max_cardinality": result.cost.max_cardinality,
            "join_depth": result.cost.join_depth,
            "cost": result.cost.cost,
            "explanation": result.cost.explanation,
        },
        "needs_approval": needs_approval,
        "threshold": threshold,
        "referenced_tables": result.referenced_tables,
    }
    if needs_approval:
        response["cost_gate_trigger"] = {
            "explain": result.plan,
            "estimated_cost": result.cost.cost,
            "threshold": threshold,
            "engine": "duckdb",
            "referenced_tables": result.referenced_tables,
        }
        from pointlessql.services.governance_events import (
            EVENT_TYPE_COST_GATE_DENIED,
            emit_governance_event,
        )

        factory = getattr(request.app.state, "session_factory", None)
        try:
            await emit_governance_event(
                EVENT_TYPE_COST_GATE_DENIED,
                {
                    "principal": email,
                    "estimated_cost": result.cost.cost,
                    "threshold": threshold,
                    "referenced_tables": result.referenced_tables,
                    "query_hash": short_sql_hash(query),
                },
                settings=settings,
                session_factory=factory,
            )
        except Exception:  # noqa: BLE001 — emit must never raise
            logger.exception("cost_gate.denied emit failed for %s", short_sql_hash(query))
    return response


@router.get("/sql", response_class=HTMLResponse)
async def sql_editor_page(request: Request) -> HTMLResponse:
    """Render the SQL editor page."""
    settings: Settings = request.app.state.settings
    return _templates(request).TemplateResponse(
        request,
        "pages/sql_editor.html",
        {
            "sql_enabled": settings.sql.enabled,
            "active_page": "sql",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
