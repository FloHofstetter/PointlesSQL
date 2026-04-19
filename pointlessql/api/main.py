"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import Body, FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import (
    audit as _audit,
)
from pointlessql.api._audit_helpers import (
    record_query_async as _record_query_async,
)
from pointlessql.api.auth_routes import router as auth_router
from pointlessql.api.catalog_routes import router as catalog_router
from pointlessql.api.dependencies import (
    get_uc_client as _get_uc_client,
)
from pointlessql.api.dependencies import (
    get_user as _get_user,
)
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.middleware import register_middleware
from pointlessql.db import get_session_factory, init_db
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogUnavailableError,
    PointlessSQLError,
    ValidationError,
)
from pointlessql.logging_config import configure_logging
from pointlessql.services import audit as audit_service
from pointlessql.services import auth as auth_service
from pointlessql.services import kernel_session as kernel_session_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import notebook_outputs as notebook_outputs_service
from pointlessql.services import notebook_render as notebook_render_service
from pointlessql.services import notebook_workspace as notebook_workspace_service
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services import pyright_bridge as pyright_bridge_service
from pointlessql.services import query_history as query_history_service
from pointlessql.services import saved_queries as saved_queries_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    MODIFY,
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    check_privilege,
    check_privilege_from_effective,
    has_privilege,
)
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = Settings()
configure_logging(_startup_settings.logging.level, _startup_settings.logging.format)

logger = logging.getLogger(__name__)

# In a dev checkout the frontend dir is at the repo root; in an
# installed wheel hatchling force-includes it as pointlessql/_frontend.
_dev_dir = Path(__file__).resolve().parents[2] / "frontend"
_FRONTEND_DIR = _dev_dir if _dev_dir.is_dir() else Path(__file__).resolve().parents[1] / "_frontend"
_TEMPLATES = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))


def _format_epoch_ms(value: Any) -> str:
    """Format Unity Catalog epoch-millisecond timestamps as a local datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except TypeError, ValueError:
        return str(value)


_TEMPLATES.env.filters["epoch_ms"] = _format_epoch_ms


_original_template_response = _TEMPLATES.TemplateResponse


def _template_response_with_user(request: Request, *args: Any, **kwargs: Any) -> Response:
    """Wrap TemplateResponse to inject ``current_user`` into every context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    if "context" in kwargs:
        kwargs["context"].setdefault("current_user", getattr(request.state, "user", None))
    elif len(args) >= 2 and isinstance(args[1], dict):
        mutable = list(args)
        mutable[1].setdefault("current_user", getattr(request.state, "user", None))
        args = tuple(mutable)
    return _original_template_response(request, *args, **kwargs)


_TEMPLATES.TemplateResponse = _template_response_with_user  # type: ignore[assignment]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared services and manage the Jupyter subprocess."""
    settings = Settings()
    logger.info(
        "PointlesSQL starting on %s:%d (engine=%s, log_format=%s)",
        settings.server.host,
        settings.server.port,
        settings.delta.engine,
        settings.logging.format,
    )
    soyuz = make_soyuz_client(settings)
    app.state.uc_client = UnityCatalogClient(soyuz)
    app.state.settings = settings
    app.state.templates = _TEMPLATES

    init_db(settings.db.url)
    app.state.session_factory = get_session_factory()

    scheduler: scheduler_service.Scheduler | None = None
    if settings.scheduler.enabled:
        scheduler = scheduler_service.Scheduler(app.state.session_factory, settings)
        scheduler.start()
    app.state.scheduler = scheduler

    # Sprint 48: periodic audit-log retention sweep. Runs on its own
    # tick cadence (``audit.cleanup_interval_seconds``) so it does
    # not compete with the job scheduler; swallows its own errors
    # via ``cleanup_old_entries`` so a transient DB hiccup never
    # takes the lifespan down.
    audit_task = asyncio.create_task(
        _audit_retention_loop(app.state.session_factory, settings),
        name="audit-retention",
    )

    kernel_registry = kernel_session_service.KernelRegistry(
        settings.jupyter.notebooks_dir.resolve()
    )
    app.state.kernel_registry = kernel_registry

    # Sprint 63: the embedded JupyterLab subprocess is retired.  The
    # native Phase-12.6 editor + per-notebook ipykernel registry
    # (Sprint 59) serve every notebook-facing use case; papermill
    # spawns its own kernel per run.  Nothing else to start here.
    try:
        yield
    finally:
        audit_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await audit_task
        if scheduler is not None:
            await scheduler.stop()
        await kernel_registry.shutdown_all()
        await app.state.uc_client.aclose()


async def _audit_retention_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Run ``cleanup_old_entries`` on a fixed cadence for the lifetime of the app.

    A separate task rather than a scheduler-kind keeps the
    cleanup path independent of the job scheduler — operators who
    disable the scheduler (``POINTLESSQL_SCHEDULER_ENABLED=false``)
    still want retention to run.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings` — only
            ``audit.retention_days`` and
            ``audit.cleanup_interval_seconds`` are read.
    """
    interval = max(60, settings.audit.cleanup_interval_seconds)
    retention = settings.audit.retention_days
    while True:
        try:
            await asyncio.to_thread(
                audit_service.cleanup_old_entries, factory, retention
            )
        except Exception:  # noqa: BLE001 — retention loop must survive everything
            logger.exception("audit: retention loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)

from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

app.include_router(auth_router)
app.include_router(catalog_router)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

register_middleware(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics for the scheduler (admin-only).

    Returns the default text exposition format so any Prometheus
    scraper works without extra negotiation. Gated by
    :func:`_require_admin` because the metrics surface includes the
    names of every job in the install, which is sensitive information
    on multi-tenant deployments.
    """
    _require_admin(request)
    body, content_type = metrics_service.render_metrics()
    return Response(content=body, media_type=content_type)


# -- JSON API routes --
# Exceptions propagate to the centralized handler in error_handlers.py.
# Catalog tree routes (/api/tree, /api/catalogs, /api/catalogs/.../schemas,
# .../tables, .../preview) live in api/catalog_routes.py since Sprint 86.


def _short_sql_hash(sql: str) -> str:
    """Return a short deterministic digest of *sql* for audit-log targets.

    The audit-log ``target`` field is a single human-readable identifier
    (``catalog:foo``, ``query:abc123``…); a full SQL string would blow
    past the reasonable column width.  A 12-char truncated SHA-256 is
    enough to correlate with the ``query_history`` row landing in
    Sprint 50 and to tell apart identical-looking queries.

    Args:
        sql: The SQL string to hash.

    Returns:
        A 12-character hexadecimal digest.
    """
    import hashlib

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def _run_sql_sync(
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


def _live_queries(request: Request) -> dict[str, Any]:
    """Return the per-app live-queries registry, creating it on first use.

    Stored on ``app.state._live_queries`` so every worker in the same
    process shares one dict.  Keys are client-supplied query IDs
    (UUIDs); values are live :class:`duckdb.DuckDBPyConnection`
    handles.  The execute route registers on entry and pops on exit;
    the cancel route calls ``.interrupt()`` on whatever it finds.
    Multi-worker deployments don't share this map across processes —
    Sprint 52 accepts single-worker correctness; multi-worker cancel
    is a Phase-14 concern.

    Args:
        request: The incoming request (for ``request.app.state``).

    Returns:
        The mutable registry dict (live for the app's lifetime).
    """
    registry: dict[str, Any] | None = getattr(
        request.app.state, "_live_queries", None
    )
    if registry is None:
        registry = {}
        request.app.state._live_queries = registry
    return registry


@app.post("/api/sql/execute")
async def api_sql_execute(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Parse, enforce, execute a single SELECT against the UC lakehouse.

    Flow (Sprint 49 scope):

    1. Parse via :func:`~pointlessql.pql.sql_parser.prepare_sql` to
       extract the 3-part table references and a DuckDB-safe rewrite
       of the SQL.
    2. For every referenced table: fetch ``storage_location`` from
       soyuz-catalog and call ``check_privilege(SELECT)``.  Admin
       short-circuits per :mod:`pointlessql.services.authorization`.
    3. Dispatch :meth:`PQL.sql` via :func:`asyncio.to_thread` so the
       event loop keeps serving other requests during the DuckDB
       call.
    4. Audit the execution with the Phase-12 ``query.executed``
       action string (per ROADMAP settled decision).

    Sprint 49 explicit non-goals: history (50), save (51), export
    (52), EXPLAIN / autocomplete / cancel (52, 53).  Errors raised
    inside the parse / enforce / execute stages map to RFC 9457
    problem+json via the centralised handler.

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

    # Sprint 52: client supplies an opaque query_id the cancel
    # endpoint uses to reach the live DuckDB conn.  Empty / non-str
    # → generate one server-side so old clients keep working.
    raw_qid = (body or {}).get("query_id")
    query_id = raw_qid if isinstance(raw_qid, str) and raw_qid else uuid4().hex

    # Sprint 53: optional EXPLAIN ANALYZE mode.  The server parses
    # + enforces the raw SELECT as usual, then wraps the final
    # statement with ``EXPLAIN ANALYZE``.  Diagnostic runs skip
    # history recording + audit to keep the operator-facing
    # surfaces clean.
    explain = bool((body or {}).get("explain", False))

    started_at = datetime.now(UTC)
    parsed_refs: list[str] = []
    cancelled = False
    timed_out = False
    conn: Any = None
    registry = _live_queries(request)
    try:
        try:
            prepared = prepare_sql(query)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc
        parsed_refs = list(prepared.refs)

        client = _get_uc_client(request)
        user = _get_user(request)
        email = user.get("email", "")
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

        # Sprint 52: open the connection here and hand it to the
        # thread so the cancel endpoint can reach ``.interrupt()``
        # via the live-queries registry.
        conn = duckdb.connect()
        registry[query_id] = conn
        timeout_s = max(1, int(settings.sql.query_timeout_seconds))
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    _run_sql_sync,
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
            await _record_query_async(
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
        history_id = await _record_query_async(
            request,
            sql_text=query,
            started_at=started_at,
            finished_at=finished_at,
            status="succeeded",
            row_count=result.row_count,
            duration_ms=result.duration_ms,
            referenced_tables=result.referenced_tables,
        )
        await _audit(
            request,
            "query.executed",
            f"query:{_short_sql_hash(query)}",
            {
                "row_count": result.row_count,
                "duration_ms": result.duration_ms,
                "tables": result.referenced_tables,
                "truncated": result.truncated,
            },
        )

    explain_text: str | None = None
    if explain:
        # DuckDB returns EXPLAIN ANALYZE as a set of rows with
        # column(s) like ``explain_key`` / ``explain_value``.
        # Flatten everything into a single monospace blob that
        # the frontend can drop straight into a <pre>.
        lines: list[str] = []
        for row in result.rows:
            lines.append("\t".join("" if cell is None else str(cell) for cell in row))
        explain_text = "\n".join(lines)

    return {
        "query_id": query_id,
        "history_id": history_id,
        "is_explain": explain,
        "explain_text": explain_text,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
        "executed_sql": result.executed_sql,
        "referenced_tables": result.referenced_tables,
    }


@app.post("/api/sql/execute/{query_id}/cancel", status_code=204)
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
    registry = _live_queries(request)
    conn = registry.get(query_id)
    if conn is not None:
        try:
            conn.interrupt()
        except Exception as exc:  # noqa: BLE001 — diagnostic only
            logger.warning("conn.interrupt() raised on cancel: %s", exc)
    await _audit(request, "query.cancelled", f"query_id:{query_id}", None)
    return Response(status_code=204)


def _run_sql_export_sync(
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


@app.get("/api/sql/execute/{history_id}/download")
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

    user = _get_user(request)
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

    client = _get_uc_client(request)
    email = user.get("email", "")
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
        _run_sql_export_sync,
        settings,
        row.sql_text,
        approved,
        settings.sql.max_rows,
    )

    fmt = format.lower()
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"query-{history_id}-{ts}.{fmt}"
    await _audit(
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


@app.get("/sql", response_class=HTMLResponse)
async def sql_editor_page(request: Request) -> HTMLResponse:
    """Render the Phase-12 SQL editor page."""
    settings: Settings = request.app.state.settings
    return _TEMPLATES.TemplateResponse(
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


def _parse_since(raw: str | None) -> datetime | None:
    """Map a ``?since=`` query param to a cutoff datetime.

    Accepts ``24h``, ``7d``, ``30d``, ``all``, or ``None``.  Any other
    value maps to ``None`` (no filter) — invalid input should never
    reject the whole page.

    Args:
        raw: The raw query-string value.

    Returns:
        The cutoff :class:`datetime` in UTC, or ``None`` for
        ``"all"`` / unparseable / missing.
    """
    if not raw or raw == "all":
        return None
    mapping = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = mapping.get(raw)
    if delta is None:
        return None
    return datetime.now(UTC) - delta


@app.get("/api/queries")
async def api_list_queries(
    request: Request,
    *,
    user_id: int | None = None,
    status: str | None = None,
    since: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent query-history rows as JSON.

    Non-admin callers see only their own rows — the ``user_id``
    query param is clamped to the caller's ID regardless of what
    was requested (Sprint-50 parity with ``/api/jobs`` from Sprint
    33).  Admin can pass ``user_id=123`` to scope or ``None`` to
    see everyone.

    Args:
        request: Incoming request (for the current user).
        user_id: Optional user-ID filter (admin only).
        status: Optional status filter.
        since: Window string (``24h`` / ``7d`` / ``30d`` / ``all``).
        limit: Hard row cap (default 200).

    Returns:
        A list of history dicts — see
        :func:`pointlessql.services.query_history.list_queries`.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = _get_user(request)
    if not user.get("is_admin"):
        user_id = user["id"]
    effective_limit = max(1, min(int(limit), 1000))
    return await asyncio.to_thread(
        query_history_service.list_queries,
        factory,
        user_id=user_id,
        status=status,
        since=_parse_since(since),
        limit=effective_limit,
    )


@app.get("/api/queries/{history_id}")
async def api_get_query(request: Request, history_id: int) -> dict[str, Any]:
    """Return a single ``query_history`` row as JSON.

    Used by the Sprint-54 chart-replay flow: the editor fetches a
    row by id to seed its chart config when the user opens a deep
    link.  404 collapses ``missing`` and ``forbidden`` so an
    unprivileged caller cannot probe IDs.

    Args:
        request: Incoming request (for the current user).
        history_id: ``query_history.id`` to fetch.

    Returns:
        The history row dict.

    Raises:
        CatalogNotFoundError: If the row is missing or invisible.
    """  # noqa: DOC502,DOC503 — raised below
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    user = _get_user(request)
    row = await asyncio.to_thread(
        query_history_service.get_by_id,
        factory,
        history_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if row is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    return row


@app.patch("/api/queries/{history_id}/chart-config")
async def api_update_query_chart_config(
    request: Request,
    history_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Persist the user's chart selection for a history row.

    The body carries ``chart_config`` as either a dict (stored
    canonically as ``json.dumps``-serialised text) or ``null`` to
    clear the persisted selection.  Only the row owner and admin
    users may mutate.

    Args:
        request: Incoming request.
        history_id: ``query_history.id`` to update.
        body: Mapping with a ``chart_config`` key carrying either a
            dict ``{type, x, y}`` or ``null``.

    Returns:
        The updated history row dict.

    Raises:
        CatalogNotFoundError: If the row is missing or not owned by
            the caller (admins exempt).
        ValidationError: If ``chart_config`` is present but is neither
            a mapping nor ``null``.
    """  # noqa: DOC502,DOC503 — raised below
    from pointlessql.exceptions import CatalogNotFoundError, ValidationError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    user = _get_user(request)
    payload = body or {}
    raw = payload.get("chart_config")
    if raw is None:
        serialised: str | None = None
    elif isinstance(raw, dict):
        serialised = json.dumps(raw, separators=(",", ":"), sort_keys=True)
    else:
        raise ValidationError("chart_config must be an object or null.")
    row = await asyncio.to_thread(
        query_history_service.update_chart_config,
        factory,
        history_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        chart_config=serialised,
    )
    if row is None:
        raise CatalogNotFoundError(f"Query {history_id} not found.")
    await _audit(
        request,
        "query.chart_config_updated",
        f"query_history:{history_id}",
        {"cleared": serialised is None},
    )
    return row


@app.get("/queries", response_class=HTMLResponse)
async def queries_page(request: Request) -> HTMLResponse:
    """Render the Phase-12 query history page.

    Pre-loads the initial history slice server-side so the page
    paints without waiting on a second round-trip; the list-table
    Alpine component then takes over for chip filtering and sort.
    """
    factory = getattr(request.app.state, "session_factory", None)
    user = _get_user(request)
    entries: list[dict[str, Any]] = []
    if factory is not None:
        user_filter: int | None = None if user.get("is_admin") else user["id"]
        entries = await asyncio.to_thread(
            query_history_service.list_queries,
            factory,
            user_id=user_filter,
            limit=200,
        )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/queries.html",
        {
            "entries": entries,
            "active_page": "queries",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


# -- Phase 12 saved queries (Sprint 51) ------------------------------------


@app.get("/api/saved-queries")
async def api_list_saved_queries(request: Request) -> list[dict[str, Any]]:
    """Return every saved query visible to the current user.

    Admin sees all rows; non-admin sees their own + every row
    with ``is_shared = True``.  Ordered by ``updated_at`` so the
    most recent edits float to the top.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = _get_user(request)
    return await asyncio.to_thread(
        saved_queries_service.list_visible,
        factory,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )


@app.post("/api/saved-queries")
async def api_create_saved_query(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a new saved query owned by the current user.

    Args:
        request: The incoming FastAPI request.
        body: JSON body with ``title``, ``sql`` (or ``sql_text``),
            optional ``description`` and ``is_shared``.

    Returns:
        The serialised row as a dict.

    Raises:
        ValidationError: If ``title`` or the SQL field is missing
            / empty.
    """  # noqa: DOC502 — raised by services.saved_queries.create_saved_query
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ValidationError("Saved queries unavailable: no session factory bound.")
    user = _get_user(request)
    payload = body or {}
    title = payload.get("title", "")
    description = payload.get("description")
    sql_text = payload.get("sql_text") or payload.get("sql") or ""
    is_shared = bool(payload.get("is_shared", False))
    row = await asyncio.to_thread(
        saved_queries_service.create_saved_query,
        factory,
        owner_id=user["id"],
        title=title if isinstance(title, str) else "",
        description=description if isinstance(description, str) else None,
        sql_text=sql_text if isinstance(sql_text, str) else "",
        is_shared=is_shared,
    )
    action = "query.shared" if row["is_shared"] else "query.saved"
    await _audit(request, action, f"saved_query:{row['slug']}", {"title": row["title"]})
    return row


@app.get("/api/saved-queries/{slug}")
async def api_get_saved_query(request: Request, slug: str) -> dict[str, Any]:
    """Return a saved query by slug or 404 if hidden/missing.

    Args:
        request: The incoming request.
        slug: The saved-query slug.

    Returns:
        The serialised row.

    Raises:
        CatalogNotFoundError: If the slug does not exist or the
            current user cannot see it.  We collapse "not found"
            and "forbidden" so private slugs are not discoverable.
    """  # noqa: DOC502 — CatalogNotFoundError raised via module import below
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = _get_user(request)
    row = await asyncio.to_thread(
        saved_queries_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    return row


@app.patch("/api/saved-queries/{slug}")
async def api_update_saved_query(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Update a saved query.  Only owner + admin may mutate.

    Args:
        request: The incoming request.
        slug: The slug of the row to update.
        body: Partial update payload — ``title``, ``description``,
            ``sql_text`` / ``sql``, ``is_shared``.  Any field not
            present is left unchanged.

    Returns:
        The updated row as a dict.

    Raises:
        CatalogNotFoundError: If the row is missing or the user
            is not the owner / admin.  (We do not differentiate
            so unauthorised clients cannot probe for existence.)
        ValidationError: If a non-``None`` title / sql is empty.
    """  # noqa: DOC502,DOC503 — raised by saved_queries.update_by_slug
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = _get_user(request)
    payload = body or {}
    previous = await asyncio.to_thread(
        saved_queries_service.get_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    row = await asyncio.to_thread(
        saved_queries_service.update_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        description=payload.get("description")
        if isinstance(payload.get("description"), str)
        else None,
        sql_text=payload.get("sql_text")
        if isinstance(payload.get("sql_text"), str)
        else (payload.get("sql") if isinstance(payload.get("sql"), str) else None),
        is_shared=bool(payload.get("is_shared"))
        if "is_shared" in payload
        else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")

    action = "query.updated"
    if previous is not None and previous["is_shared"] != row["is_shared"]:
        action = "query.shared" if row["is_shared"] else "query.unshared"
    await _audit(request, action, f"saved_query:{slug}", {"title": row["title"]})
    return row


@app.delete("/api/saved-queries/{slug}", status_code=204)
async def api_delete_saved_query(request: Request, slug: str) -> Response:
    """Delete a saved query.  Only owner + admin may delete.

    Args:
        request: The incoming request.
        slug: The slug of the row to delete.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: If the row is missing or the user
            is not owner / admin.
    """  # noqa: DOC502 — raised via service return value check
    from pointlessql.exceptions import CatalogNotFoundError

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    user = _get_user(request)
    ok = await asyncio.to_thread(
        saved_queries_service.delete_by_slug,
        factory,
        slug,
        user_id=user["id"],
        is_admin=user.get("is_admin", False),
    )
    if not ok:
        raise CatalogNotFoundError(f"Saved query {slug!r} not found.")
    await _audit(request, "query.deleted", f"saved_query:{slug}", None)
    return Response(status_code=204)


# -- Phase 12.5 / Sprint 55: query alerts ----------------------------------


def _base_url(request: Request) -> str:
    """Return the absolute base URL for the running deployment.

    Args:
        request: Incoming request used to build the URL.

    Returns:
        ``<scheme>://<host>`` without trailing slash.
    """
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _rotate_or_fetch_feed_token(
    factory: Any, user_id: int, rotate: bool = False
) -> str:
    """Return the caller's feed token, materialising one on first access.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Authenticated user id.
        rotate: When ``True`` force a fresh token even if one exists.

    Returns:
        URL-safe opaque token.

    Raises:
        RuntimeError: When the authenticated user id no longer
            resolves to a row (shouldn't happen since the request
            already authenticated, but kept explicit).
    """
    import secrets as _secrets

    from pointlessql.models import User

    with factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        if not user.feed_token or rotate:
            user.feed_token = _secrets.token_urlsafe(32)
            session.commit()
            session.refresh(user)
        return user.feed_token or ""


def _user_for_feed_token(factory: Any, token: str) -> Any:
    """Return the :class:`User` matching *token*, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        token: Opaque token from the query string.

    Returns:
        The user row or ``None`` when the token does not resolve.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import User

    if not token:
        return None
    with factory() as session:
        return session.scalar(
            _select(User).where(User.feed_token == token)
        )


@app.get("/api/alerts")
async def api_list_alerts(request: Request) -> list[dict[str, Any]]:
    """List alerts visible to the caller.

    Non-admin callers only see their own alerts; admin sees every row.

    Args:
        request: Incoming request (for the current user).

    Returns:
        Serialised alerts with embedded destinations.
    """
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return []
    user = _get_user(request)
    return await asyncio.to_thread(
        alerts_service.list_visible,
        factory,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )


@app.post("/api/alerts")
async def api_create_alert(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a new alert owned by the caller.

    Args:
        request: Incoming request.
        body: JSON body with ``title``, ``saved_query_id``,
            ``cron_expr``, ``condition_op``, ``threshold`` keys;
            optional ``is_active`` (defaults ``True``).

    Returns:
        The serialised alert dict.

    Raises:
        ValidationError: If any required field fails validation.
    """  # noqa: DOC502 — ValidationError raised by service layer
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise ValidationError("Alerts are not available in this deployment.")
    user = _get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        alerts_service.create_alert,
        factory,
        owner_id=user["id"],
        title=str(payload.get("title", "")),
        saved_query_id=int(payload.get("saved_query_id") or 0),
        cron_expr=str(payload.get("cron_expr", "")),
        condition_op=str(payload.get("condition_op", "gt")),
        threshold=int(payload.get("threshold", 0)),
        is_active=bool(payload.get("is_active", True)),
    )
    await _audit(
        request,
        "alert.created",
        f"alert:{row['slug']}",
        {"title": row["title"], "cron_expr": row["cron_expr"]},
    )
    return row


@app.get("/api/alerts/{slug}")
async def api_get_alert(request: Request, slug: str) -> dict[str, Any]:
    """Return a single alert by slug.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        Serialised alert with destinations.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    row = await asyncio.to_thread(
        alerts_service.get_by_slug,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    return row


@app.patch("/api/alerts/{slug}")
async def api_update_alert(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Partially update an alert.  Only owner + admin may mutate.

    Args:
        request: Incoming request.
        slug: Alert slug.
        body: Partial update payload.

    Returns:
        Updated alert dict.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below; ValidationError bubbles from service
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        alerts_service.update_by_slug,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        cron_expr=payload.get("cron_expr")
        if isinstance(payload.get("cron_expr"), str) else None,
        condition_op=payload.get("condition_op")
        if isinstance(payload.get("condition_op"), str) else None,
        threshold=int(payload["threshold"])
        if isinstance(payload.get("threshold"), int) else None,
        is_active=bool(payload["is_active"])
        if "is_active" in payload else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await _audit(
        request, "alert.updated", f"alert:{slug}",
        {"is_active": row["is_active"]},
    )
    return row


@app.delete("/api/alerts/{slug}", status_code=204)
async def api_delete_alert(request: Request, slug: str) -> Response:
    """Delete an alert, its destinations, events, and backing Job.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    ok = await asyncio.to_thread(
        alerts_service.delete_by_slug,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await _audit(request, "alert.deleted", f"alert:{slug}", None)
    return Response(status_code=204)


@app.post("/api/alerts/{slug}/destinations")
async def api_add_alert_destination(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Add a webhook or feed destination to an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        body: Body with ``kind`` (``webhook`` / ``feed``), plus
            ``webhook_url`` / ``hmac_secret`` when relevant.

    Returns:
        The new destination dict.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below; ValidationError bubbles from service
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    payload = body or {}
    dest = await asyncio.to_thread(
        alerts_service.add_destination,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        kind=str(payload.get("kind", "webhook")),
        webhook_url=payload.get("webhook_url")
        if isinstance(payload.get("webhook_url"), str) else None,
        hmac_secret=payload.get("hmac_secret")
        if isinstance(payload.get("hmac_secret"), str) else None,
    )
    if dest is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await _audit(
        request, "alert.destination_added", f"alert:{slug}",
        {"kind": dest["kind"], "has_hmac": dest["has_hmac"]},
    )
    return dest


@app.delete(
    "/api/alerts/{slug}/destinations/{destination_id}", status_code=204
)
async def api_delete_alert_destination(
    request: Request, slug: str, destination_id: int
) -> Response:
    """Remove a destination from an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        destination_id: Row id of the destination.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    ok = await asyncio.to_thread(
        alerts_service.delete_destination,
        factory, slug, destination_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await _audit(
        request, "alert.destination_removed",
        f"alert:{slug}/destination:{destination_id}", None,
    )
    return Response(status_code=204)


@app.get("/api/me/feed-token")
async def api_get_feed_token(request: Request) -> dict[str, str]:
    """Return the caller's pull-feed token, creating one on first call.

    Args:
        request: Incoming request.

    Returns:
        Dict with ``token`` key.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"token": ""}
    user = _get_user(request)
    token = await asyncio.to_thread(
        _rotate_or_fetch_feed_token, factory, user["id"], False
    )
    return {"token": token}


@app.post("/api/me/feed-token/rotate")
async def api_rotate_feed_token(request: Request) -> dict[str, str]:
    """Rotate the caller's feed token, invalidating existing subscribers.

    Args:
        request: Incoming request.

    Returns:
        Dict with the new ``token``.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"token": ""}
    user = _get_user(request)
    token = await asyncio.to_thread(
        _rotate_or_fetch_feed_token, factory, user["id"], True
    )
    await _audit(request, "alert.feed_token_rotated", f"user:{user['id']}", None)
    return {"token": token}


@app.get("/alerts/feed.atom")
async def feed_atom(request: Request, token: str = "") -> Response:
    """Serve a per-owner Atom 1.0 feed of fired alerts.

    Args:
        request: Incoming request (used for base-URL building).
        token: Opaque per-user token from the query string.

    Returns:
        200 with Atom XML body on success, 401 on token mismatch.
    """
    from pointlessql.services import alert_feeds
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=401)
    user = await asyncio.to_thread(_user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await asyncio.to_thread(
        alerts_service.list_events_for_owner,
        factory, user.id, since=cutoff, limit=200,
    )
    body = alert_feeds.render_atom(
        events, user_email=user.email, base_url=_base_url(request),
    )
    return Response(
        content=body,
        media_type="application/atom+xml; charset=utf-8",
    )


@app.get("/alerts/feed.json")
async def feed_json(request: Request, token: str = "") -> Response:
    """Serve a per-owner JSON Feed 1.1 document of fired alerts.

    Args:
        request: Incoming request.
        token: Opaque per-user token.

    Returns:
        200 with JSON Feed body on success, 401 on token mismatch.
    """
    from pointlessql.services import alert_feeds
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=401)
    user = await asyncio.to_thread(_user_for_feed_token, factory, token)
    if user is None:
        return Response(status_code=401)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    events = await asyncio.to_thread(
        alerts_service.list_events_for_owner,
        factory, user.id, since=cutoff, limit=200,
    )
    body = alert_feeds.render_json_feed(
        events, user_email=user.email, base_url=_base_url(request),
    )
    return JSONResponse(content=body, media_type="application/feed+json")


@app.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request) -> HTMLResponse:
    """Render the alerts list page.

    Args:
        request: Incoming request.

    Returns:
        HTML page with the list of visible alerts.
    """
    from pointlessql.services import alerts as alerts_service
    from pointlessql.services import saved_queries as saved_queries_service

    factory = getattr(request.app.state, "session_factory", None)
    user = _get_user(request)
    alerts: list[dict[str, Any]] = []
    saved: list[dict[str, Any]] = []
    if factory is not None:
        alerts = await asyncio.to_thread(
            alerts_service.list_visible,
            factory,
            user_id=user["id"],
            is_admin=bool(user.get("is_admin", False)),
        )
        saved = await asyncio.to_thread(
            saved_queries_service.list_visible,
            factory,
            user_id=user["id"],
            is_admin=bool(user.get("is_admin", False)),
            limit=200,
        )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/alerts.html",
        {
            "alerts": alerts,
            "saved_queries": saved,
            "active_page": "alerts",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@app.get("/alerts/{slug}", response_class=HTMLResponse)
async def alert_detail_page(request: Request, slug: str) -> HTMLResponse:
    """Render the alert detail page with recent events.

    Args:
        request: Incoming request.
        slug: Alert slug.

    Returns:
        HTML page with the alert's destinations + last 50 events.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = _get_user(request)
    alert_row = await asyncio.to_thread(
        alerts_service.get_by_slug,
        factory, slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if alert_row is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    events = await asyncio.to_thread(
        alerts_service.list_events_for_alert,
        factory, alert_row["id"], limit=50,
    )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/alert_detail.html",
        {
            "alert": alert_row,
            "events": events,
            "active_page": "alerts",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Phase 12.5 / Sprint 57: UC volumes (files + convert-to-Delta) ---------


def _soyuz_base_url(request: Request) -> str:
    """Return the configured soyuz-catalog base URL.

    Args:
        request: Incoming request.

    Returns:
        The base URL string (without trailing slash).
    """
    settings: Settings = request.app.state.settings
    return settings.soyuz.catalog_url.rstrip("/")


async def _volume_full_name_split(full_name: str) -> tuple[str, str, str]:
    """Split *full_name* into its UC three parts or raise.

    Args:
        full_name: Dotted identifier.

    Returns:
        Tuple ``(catalog, schema, volume)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.volume, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]


@app.get("/api/volumes/{full_name:path}/files")
async def api_browse_volume(
    request: Request, full_name: str
) -> dict[str, list[dict[str, Any]]]:
    """List every file stored on *full_name*.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.

    Returns:
        Dict with a ``files`` list in soyuz's serialisation.
    """
    from pointlessql.services import volumes as vol_service

    await _volume_full_name_split(full_name)
    user = _get_user(request)
    async with httpx.AsyncClient() as client:
        files = await vol_service.browse_files(
            client, _soyuz_base_url(request), full_name,
            principal=user.get("email"),
        )
    return {"files": files}


@app.post("/api/volumes/{full_name:path}/files")
async def api_upload_volume_file(
    request: Request,
    full_name: str,
    path: str = Form(...),
    upload: UploadFile = File(...),
) -> dict[str, Any]:
    """Proxy a multipart upload into soyuz's volume storage backend.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        path: Volume-relative destination path.
        upload: The ``multipart/form-data`` body.

    Returns:
        Dict with the resulting file entry.
    """
    from pointlessql.services import volumes as vol_service

    await _volume_full_name_split(full_name)
    user = _get_user(request)
    data = await upload.read()
    async with httpx.AsyncClient() as client:
        body = await vol_service.upload_file(
            client,
            _soyuz_base_url(request),
            full_name,
            path=path,
            upload_name=upload.filename or path,
            upload_bytes=data,
            principal=user.get("email"),
            content_type=upload.content_type or "application/octet-stream",
        )
    await _audit(
        request, "volume.file_uploaded", f"volume:{full_name}",
        {"path": path, "bytes": len(data)},
    )
    return body


@app.delete("/api/volumes/{full_name}/files/{path:path}", status_code=204)
async def api_delete_volume_file(
    request: Request, full_name: str, path: str
) -> Response:
    """Remove a single file from a volume.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        path: Volume-relative source path.

    Returns:
        Empty 204.
    """
    from pointlessql.services import volumes as vol_service

    await _volume_full_name_split(full_name)
    user = _get_user(request)
    async with httpx.AsyncClient() as client:
        await vol_service.delete_file(
            client, _soyuz_base_url(request), full_name, path,
            principal=user.get("email"),
        )
    await _audit(
        request, "volume.file_deleted", f"volume:{full_name}",
        {"path": path},
    )
    return Response(status_code=204)


def _convert_volume_file_sync(
    settings: Settings,
    *,
    source_file: Path,
    source_format: str,
    target_location: str,
) -> None:
    """Read *source_file* via DuckDB and write it as a Delta table.

    Runs under ``asyncio.to_thread`` so the request handler keeps
    serving other requests during the convert pass.

    Args:
        settings: Application settings (reserved; forward-compatible
            hook for engine selection).
        source_file: Absolute path of the CSV / Parquet / JSON source.
        source_format: ``"csv"`` / ``"parquet"`` / ``"json"``.
        target_location: ``file://`` URI for the managed Delta output.

    Raises:
        ValidationError: On an unsupported ``source_format``.
    """
    import duckdb

    del settings
    reader = {
        "csv": "read_csv_auto",
        "parquet": "read_parquet",
        "json": "read_json_auto",
    }.get(source_format)
    if reader is None:
        raise ValidationError(
            f"Unsupported convert source format {source_format!r}; "
            "expected one of csv / parquet / json.",
        )
    conn = duckdb.connect()
    try:
        arrow_table = conn.execute(
            f"SELECT * FROM {reader}('{source_file}')"
        ).to_arrow_table()
    finally:
        conn.close()
    # deltalake writes the target dir in place; target_location may
    # be a file:// URI which deltalake accepts verbatim.
    import deltalake

    deltalake.write_deltalake(target_location, arrow_table, mode="overwrite")


# Delta ``PrimitiveType.type`` string → UC ``(type_name, type_text)``.
# Mirrors the DuckDB / UC type codes used by
# :mod:`pointlessql.pql.engine` for sync-path table rows, but keyed
# off the Delta schema surface rather than the DuckDB one so the
# convert-to-Delta flow can register columns with correct numeric
# types instead of falling back to ``string``.
_DELTA_PRIMITIVE_TO_UC: dict[str, tuple[str, str]] = {
    "boolean": ("BOOLEAN", "boolean"),
    "byte": ("BYTE", "byte"),
    "short": ("SHORT", "short"),
    "integer": ("INT", "int"),
    "long": ("LONG", "long"),
    "float": ("FLOAT", "float"),
    "double": ("DOUBLE", "double"),
    "date": ("DATE", "date"),
    "timestamp": ("TIMESTAMP", "timestamp"),
    "timestampntz": ("TIMESTAMP_NTZ", "timestamp_ntz"),
    "string": ("STRING", "string"),
    "binary": ("BINARY", "binary"),
}


def _delta_field_to_uc(field: Any) -> tuple[str, str]:
    """Map a ``deltalake`` schema field to UC ``(type_name, type_text)``.

    ``deltalake`` exposes a field's type as a ``PrimitiveType`` (or a
    compound type) whose ``type`` attribute is a lowercase Delta type
    code — ``"long"`` / ``"double"`` / ``"string"`` and so on.  Compound
    types (structs, arrays, maps) stringify to a JSON-like repr and
    fall back to ``("STRING", "string")`` for now; Phase-13 can map
    them properly when the agent workloads actually care.

    Args:
        field: A ``deltalake.Field``-shaped object with ``.type``.

    Returns:
        Tuple of UC ``type_name`` and ``type_text``.
    """
    prim = getattr(field.type, "type", None)
    if isinstance(prim, str):
        return _DELTA_PRIMITIVE_TO_UC.get(prim.lower(), ("STRING", "string"))
    return ("STRING", "string")


@app.post("/api/volumes/{full_name:path}/convert-to-delta")
async def api_convert_volume_file_to_delta(
    request: Request,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Read a CSV / Parquet / JSON file in the volume into a new Delta table.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.
        body: JSON body with keys:

            - ``path`` (str, required): Volume-relative source path.
            - ``table_name`` (str, required): Target table name within
              the same schema as the volume.

    Returns:
        Dict with the created table row from UC.

    Raises:
        ValidationError: If the body is missing required keys or
            points at an unsupported format.
        CatalogNotFoundError: When soyuz cannot find the volume or
            its storage is not ``file://``.
    """  # noqa: DOC502,DOC503 — raised below
    import tempfile

    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import volumes as vol_service

    user = _get_user(request)
    _require_admin(request)
    settings: Settings = request.app.state.settings
    payload = body or {}
    rel_path = payload.get("path")
    table_name = payload.get("table_name")
    if not isinstance(rel_path, str) or not rel_path:
        raise ValidationError("Body must carry a non-empty 'path'.")
    if not isinstance(table_name, str) or not table_name:
        raise ValidationError("Body must carry a non-empty 'table_name'.")

    catalog_name, schema_name, volume_name = await _volume_full_name_split(full_name)
    client = _get_uc_client(request)
    # Raw soyuz GET — the UnityCatalogClient wrapper does not expose
    # volumes yet.  Keep the call narrow; result is a dict, not a
    # typed model.
    async with httpx.AsyncClient() as http:
        v_response = await http.get(
            f"{_soyuz_base_url(request)}/api/2.1/unity-catalog/volumes/{full_name}",
            headers={"X-Principal": user.get("email") or ""},
        )
        if v_response.status_code == 404:
            raise CatalogNotFoundError(f"Volume {full_name!r} not found.")
        v_response.raise_for_status()
        volume_info = v_response.json()

    storage_location = volume_info.get("storage_location") or ""
    if not storage_location.startswith("file://"):
        raise ValidationError(
            "Convert-to-Delta currently supports only file:// volumes; "
            f"got {storage_location!r}.",
        )

    # Download the source file out of soyuz into a temp dir, convert
    # via DuckDB, write Delta under the same volume path, then
    # register a managed table in UC.
    ext = rel_path.rsplit(".", 1)[-1].lower()
    source_format = {"csv": "csv", "parquet": "parquet", "json": "json"}.get(ext)
    if source_format is None:
        raise ValidationError(
            "Unsupported source format.  Expected .csv / .parquet / .json "
            f"extension on {rel_path!r}.",
        )

    async with httpx.AsyncClient() as http_client:
        # Stream into a temp file.
        target_path = Path(tempfile.mkstemp(suffix=f".{ext}")[1])
        try:
            async for chunk in vol_service.download_file(
                http_client, _soyuz_base_url(request),
                full_name, rel_path, principal=user.get("email"),
            ):
                with target_path.open("ab") as fh:
                    fh.write(chunk)
            # Convert path: resolve a Delta target under the volume's
            # file:// root so the bytes stay inside the volume the
            # user already has rights on.
            volume_root = storage_location[len("file://"):]
            delta_dir = Path(volume_root) / f"_delta_{table_name}"
            delta_dir.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                _convert_volume_file_sync,
                settings,
                source_file=target_path,
                source_format=source_format,
                target_location=str(delta_dir),
            )
        finally:
            target_path.unlink(missing_ok=True)

    # Derive columns by peeking at the fresh Delta dir.
    import deltalake

    dt = deltalake.DeltaTable(str(delta_dir))
    schema_fields = dt.schema().fields
    columns = []
    for position, field in enumerate(schema_fields):
        type_name, type_text = _delta_field_to_uc(field)
        columns.append(
            {
                "name": field.name,
                "type_name": type_name,
                "type_text": type_text,
                "type_json": "{}",
                "type_precision": 0,
                "type_scale": 0,
                "position": position,
                "nullable": field.nullable,
            }
        )

    register_payload = {
        "name": table_name,
        "catalog_name": catalog_name,
        "schema_name": schema_name,
        "table_type": "EXTERNAL",
        "data_source_format": "DELTA",
        "columns": columns,
        "storage_location": f"file://{delta_dir}",
    }
    created = await client.create_table(register_payload)
    await _audit(
        request, "volume.converted_to_delta", f"volume:{full_name}",
        {"path": rel_path, "table": table_name, "columns": len(columns)},
    )
    _ = (catalog_name, schema_name, volume_name)  # silence unused
    return created


@app.get("/volumes", response_class=HTMLResponse)
async def volumes_page(request: Request) -> HTMLResponse:
    """Render the volumes list page.

    Iterates every catalog the caller can see and aggregates the
    per-schema volume lists from soyuz.  Non-admin callers see only
    the catalogs they hold ``USE_CATALOG`` on — enforcement already
    lives on soyuz's list endpoints.

    Args:
        request: Incoming request.

    Returns:
        HTML response.
    """
    uc_client = _get_uc_client(request)
    volumes: list[dict[str, Any]] = []
    try:
        catalogs = await uc_client.list_catalogs()
    except Exception as exc:  # noqa: BLE001 — tolerate a broken soyuz
        logger.warning("volumes page: list_catalogs failed: %s", exc)
        catalogs = []
    user = _get_user(request)
    async with httpx.AsyncClient() as http_client:
        for cat in catalogs or []:
            try:
                schemas = await uc_client.list_schemas(cat["name"])
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "volumes page: list_schemas %s failed: %s",
                    cat.get("name"), exc,
                )
                continue
            for sch in schemas or []:
                url = (
                    f"{_soyuz_base_url(request)}"
                    f"/api/2.1/unity-catalog/volumes"
                    f"?catalog_name={cat['name']}&schema_name={sch['name']}"
                )
                try:
                    resp = await http_client.get(
                        url,
                        headers={"X-Principal": user.get("email") or ""},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for v in data.get("volumes") or []:
                        volumes.append(
                            {
                                "full_name": v.get("full_name"),
                                "name": v.get("name"),
                                "catalog_name": v.get("catalog_name"),
                                "schema_name": v.get("schema_name"),
                                "storage_location": v.get("storage_location"),
                                "volume_type": v.get("volume_type"),
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("volumes page: fetch failed: %s", exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/volumes.html",
        {
            "volumes": volumes,
            "active_page": "volumes",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@app.get("/volumes/{full_name:path}", response_class=HTMLResponse)
async def volume_detail_page(request: Request, full_name: str) -> HTMLResponse:
    """Render the per-volume detail page with upload + browse surface.

    Args:
        request: Incoming request.
        full_name: Dotted UC volume identifier.

    Returns:
        HTML response.

    Raises:
        CatalogNotFoundError: When soyuz returns 404 for the volume.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import volumes as vol_service

    await _volume_full_name_split(full_name)
    user = _get_user(request)
    async with httpx.AsyncClient() as client:
        # Look up metadata via a raw soyuz GET so we can surface
        # storage_location in the UI.
        meta = await client.get(
            f"{_soyuz_base_url(request)}/api/2.1/unity-catalog/volumes/{full_name}",
            headers={"X-Principal": user.get("email") or ""},
        )
        if meta.status_code == 404:
            raise CatalogNotFoundError(f"Volume {full_name!r} not found.")
        meta.raise_for_status()
        volume = meta.json()
        files = await vol_service.browse_files(
            client, _soyuz_base_url(request), full_name,
            principal=user.get("email"),
        )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/volume_detail.html",
        {
            "volume": volume,
            "files": files,
            "active_page": "volumes",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Phase 12.5 / Sprint 56: column statistics -----------------------------


def _split_full_name(full_name: str) -> tuple[str, str, str]:
    """Split a UC three-part name, raising on bad shape.

    Args:
        full_name: Dotted identifier ``catalog.schema.table``.

    Returns:
        Tuple ``(catalog, schema, table)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.table, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]


async def _enforce_table_profile_access(
    request: Request, full_name: str
) -> dict[str, Any]:
    """Resolve table info and check that the caller may profile it.

    Admin short-circuits SELECT enforcement; every other caller must
    hold SELECT on the table before they can trigger a profile run.

    Args:
        request: Incoming request.
        full_name: Three-part UC name.

    Returns:
        The UC ``table_info`` dict.

    Raises:
        CatalogNotFoundError: When the table is missing or has no
            ``storage_location``.
        AuthorizationError: When the caller lacks SELECT on the table.
    """  # noqa: DOC502,DOC503 — raised via await below
    from pointlessql.exceptions import CatalogNotFoundError

    client = _get_uc_client(request)
    user = _get_user(request)
    email = user.get("email", "")
    is_admin = bool(user.get("is_admin", False))
    catalog, schema, table = _split_full_name(full_name)
    table_info = await client.get_table(catalog, schema, table)
    if not table_info:
        raise CatalogNotFoundError(f"Table {full_name!r} not found.")
    storage_location = table_info.get("storage_location")
    if not isinstance(storage_location, str) or not storage_location:
        raise CatalogNotFoundError(
            f"Table {full_name!r} has no storage_location on soyuz-catalog.",
        )
    await check_privilege(client, email, is_admin, "table", full_name, SELECT)
    return table_info


@app.post("/api/tables/{full_name:path}/profile")
async def api_profile_table(
    request: Request, full_name: str
) -> dict[str, Any]:
    """Compute + cache per-column statistics for the Delta table.

    The caller must hold SELECT on the table or be an administrator.
    Results are cached by ``(full_name, delta_log_version)`` so a
    second call at the same Delta version is a single index seek.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name (path-encoded).

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and a
        ``columns`` list of serialised stats rows.

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    table_info = await _enforce_table_profile_access(request, full_name)
    storage_location = str(table_info.get("storage_location") or "")
    columns = [
        {"name": str(c.get("name") or ""), "type": str(c.get("type_text") or "")}
        for c in (table_info.get("columns") or [])
        if c.get("name")
    ]
    factory = getattr(request.app.state, "session_factory", None)

    # Short-circuit: if the current version is already cached we
    # still surface it but do not recompute.
    current_version = await asyncio.to_thread(
        ts_service.read_delta_log_version, storage_location
    )
    if factory is not None:
        cached = await asyncio.to_thread(
            ts_service.read_cached,
            factory, full_name=full_name, delta_log_version=current_version,
        )
        if cached is not None:
            await _audit(
                request, "table.profile_cache_hit",
                f"table:{full_name}",
                {"delta_log_version": current_version},
            )
            return {
                "full_name": full_name,
                "delta_log_version": current_version,
                "cached": True,
                "columns": cached,
            }

    stats = await asyncio.to_thread(
        ts_service.compute_stats, full_name, storage_location, columns,
    )
    if factory is not None:
        await asyncio.to_thread(
            ts_service.write_cached,
            factory, full_name=full_name,
            delta_log_version=current_version, stats=stats,
        )
    await _audit(
        request, "table.profiled", f"table:{full_name}",
        {
            "delta_log_version": current_version,
            "column_count": len(stats),
        },
    )
    serialised = [
        {
            "column_name": col_name,
            "delta_log_version": current_version,
            "computed_at": datetime.now(UTC).isoformat(),
            "stats": stats_dict,
        }
        for col_name, stats_dict in stats.items()
    ]
    return {
        "full_name": full_name,
        "delta_log_version": current_version,
        "cached": False,
        "columns": serialised,
    }


@app.get("/api/tables/{full_name:path}/stats")
async def api_get_table_stats(
    request: Request, full_name: str, version: int | None = None
) -> dict[str, Any]:
    """Return cached stats for a UC table, optionally pinned to a version.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name.
        version: Optional Delta log version; defaults to the latest
            cached version for this table.

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and
        ``columns`` (empty list if nothing is cached yet).

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    await _enforce_table_profile_access(request, full_name)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"full_name": full_name, "delta_log_version": None, "columns": []}
    cached = await asyncio.to_thread(
        ts_service.read_cached,
        factory, full_name=full_name, delta_log_version=version,
    )
    if cached is None:
        return {"full_name": full_name, "delta_log_version": version, "columns": []}
    latest_version = max(row["delta_log_version"] for row in cached)
    return {
        "full_name": full_name,
        "delta_log_version": version if version is not None else latest_version,
        "columns": cached,
    }


@app.delete(
    "/api/tables/{full_name:path}/stats", status_code=204
)
async def api_delete_table_stats(
    request: Request, full_name: str
) -> Response:
    """Evict every cached statistics row for *full_name* (admin only).

    Args:
        request: Incoming request.
        full_name: UC three-part name.

    Returns:
        Empty 204.
    """
    from pointlessql.services import table_stats as ts_service

    _require_admin(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=204)
    removed = await asyncio.to_thread(
        ts_service.delete_cached, factory, full_name
    )
    await _audit(
        request, "table.stats_cleared", f"table:{full_name}",
        {"rows_removed": removed},
    )
    return Response(status_code=204)


@app.post("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/open-in-notebook")
async def api_open_in_notebook(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> dict[str, Any]:
    """Create a scratch ``.py`` notebook pre-filled with ``pql.table(...)``.

    Admin-only to keep the workspace clean. Sprint 63 writes a
    jupytext Percent-format ``.py`` under
    ``{notebooks_dir}/scratch/`` (one markdown cell + one code cell
    with UUID markers so the native editor picks it up on mount).
    Returns the on-disk path plus a ``/notebook/editor`` URL the
    client navigates to with ``window.location.assign``.
    """
    import secrets
    import uuid

    _require_admin(request)
    settings: Settings = request.app.state.settings
    full_name = f"{catalog_name}.{schema_name}.{table_name}"

    sanitiser = re.compile(r"[^A-Za-z0-9_-]")
    stem = "_".join(sanitiser.sub("_", part) for part in (catalog_name, schema_name, table_name))
    filename = f"{stem}_{secrets.token_hex(3)}.py"
    scratch_dir = settings.jupyter.notebooks_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    target = notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        f"scratch/{filename}",
        must_exist=False,
    )

    cells = [
        notebook_doc_service.NotebookCell(
            id=str(uuid.uuid4()),
            cell_type="markdown",
            source=(
                f"# Scratch: `{full_name}`\n\n"
                "Generated from the PointlesSQL table detail page."
            ),
        ),
        notebook_doc_service.NotebookCell(
            id=str(uuid.uuid4()),
            cell_type="code",
            source=(
                "from pointlessql import PQL\n\n"
                "pql = PQL()\n"
                f'df = pql.table("{full_name}")\n'
                "df.head()"
            ),
        ),
    ]
    notebook_doc_service.save_document(target, cells)

    await _audit(request, "open_in_notebook", f"table:{full_name}", f"scratch/{filename}")
    relative = f"scratch/{filename}"
    editor_url = f"/notebook/editor?path={relative}"
    return {"path": relative, "editor_url": editor_url}


@app.post("/api/catalogs")
async def api_create_catalog(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new catalog.

    Admin-only so foreign-catalog creation (which binds a Connection)
    stays aligned with the federation admin-only rule. Once soyuz-catalog
    exposes a finer-grained CREATE_CATALOG privilege we can switch to
    ``check_privilege`` on the metastore like the other writes.
    """
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_catalog(body)
    await _audit(request, "create_catalog", f"catalog:{body.get('name', '?')}", json.dumps(body))
    return result


@app.post("/api/catalogs/{catalog_name}/sync")
async def api_sync_catalog(request: Request, catalog_name: str) -> dict[str, object]:
    """Trigger a Postgres → UC sync for a foreign catalog (admin-only).

    Reads the catalog's bound Connection, resolves a Credential by the
    optional ``credential_name`` key in its options, and runs the
    Sprint 18 sync worker. Returns the :class:`SyncRun` snapshot so
    the UI can render the new history card entry immediately.
    """
    _require_admin(request)
    client = _get_uc_client(request)
    catalog = await client.get_catalog(catalog_name)
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise AuthorizationError(
            principal=_get_user(request).get("email", ""),
            privilege="sync",
            securable_type="catalog",
            full_name=catalog_name,
        )
    connection = await client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = options.get("credential_name") if isinstance(options, dict) else None
    if credential_name:
        credential = await client.get_credential(str(credential_name))
    factory = request.app.state.session_factory
    run = await pg_sync_service.run_sync(
        uc=client,
        factory=factory,
        catalog_name=catalog_name,
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )
    await _audit(request, "sync_catalog", f"catalog:{catalog_name}")
    return {
        "id": run.id,
        "catalog_name": run.catalog_name,
        "status": run.status,
        "added_count": run.added_count,
        "changed_count": run.changed_count,
        "dropped_count": run.dropped_count,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
    }


@app.patch("/api/catalogs/{catalog_name}")
async def api_update_catalog(
    request: Request,
    catalog_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a catalog."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        MODIFY,
    )
    result = await client.update_catalog(catalog_name, patch)
    await _audit(request, "update_catalog", f"catalog:{catalog_name}", json.dumps(patch))
    return result


@app.patch("/api/catalogs/{catalog_name}/schemas/{schema_name}")
async def api_update_schema(
    request: Request,
    catalog_name: str,
    schema_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a schema."""
    client = _get_uc_client(request)
    user = _get_user(request)
    full_name = f"{catalog_name}.{schema_name}"
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "schema",
        full_name,
        MODIFY,
    )
    result = await client.update_schema(catalog_name, schema_name, patch)
    await _audit(request, "update_schema", f"schema:{full_name}", json.dumps(patch))
    return result


@app.get("/api/tags/{securable_type}/{full_name:path}")
async def api_get_tags(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return tags for a securable."""
    client = _get_uc_client(request)
    return await client.get_tags(securable_type, full_name)


@app.patch("/api/tags/{securable_type}/{full_name:path}")
async def api_update_tags(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update tags for a securable. Body: {"changes": [...]}."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MODIFY,
    )
    result = await client.update_tags(securable_type, full_name, body.get("changes", []))
    await _audit(
        request,
        "update_tags",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@app.get("/api/permissions/{securable_type}/{full_name:path}")
async def api_get_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return privilege assignments for a securable."""
    client = _get_uc_client(request)
    return await client.get_permissions(securable_type, full_name)


@app.patch("/api/permissions/{securable_type}/{full_name:path}")
async def api_update_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update permissions for a securable. Body: {"changes": [...]}."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MANAGE_GRANTS,
    )
    result = await client.update_permissions(securable_type, full_name, body.get("changes", []))
    await _audit(
        request,
        "update_permissions",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@app.get("/api/effective-permissions/{securable_type}/{full_name:path}")
async def api_get_effective_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return effective (inherited) permissions for a securable."""
    client = _get_uc_client(request)
    return await client.get_effective_permissions(securable_type, full_name)


@app.get("/api/lineage/{full_name:path}")
async def api_lineage(request: Request, full_name: str, depth: int = 3) -> dict[str, object]:
    """Return combined upstream/downstream lineage for a table."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    return await client.get_lineage(full_name, depth)


# -- HTML pages --


@app.get("/", response_class=HTMLResponse)
async def catalogs_index(request: Request) -> HTMLResponse:
    """Render the home dashboard.

    Assembles every server-side card (catalog count, recent job runs,
    7-day sparkline, dashboards owned by the user, onboarding
    checklist) through :func:`_build_home_summary` so the first-paint
    payload matches exactly what ``/api/home/summary`` would return.
    Admins additionally get the connections list so the "Create
    foreign catalog" modal has a pre-populated dropdown.
    """
    user = _get_user(request)
    summary = await _build_home_summary(request, user)
    connections: list[dict[str, Any]] = []
    if user.get("is_admin") and not summary["catalogs"]["unavailable"]:
        try:
            connections = await _get_uc_client(request).list_connections()
        except CatalogUnavailableError:
            logger.warning("home: soyuz connections list unavailable", exc_info=True)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/home.html",
        {
            "summary": summary,
            "connections": connections,
            "is_admin": user.get("is_admin", False),
            "active_page": "home",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/catalogs/{catalog_name}", response_class=HTMLResponse)
async def catalog_detail(request: Request, catalog_name: str) -> HTMLResponse:
    """Render metadata for a single catalog."""
    client = _get_uc_client(request)
    user = _get_user(request)
    catalog: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    schemas: list[dict[str, Any]] = []
    error: str | None = None
    try:
        catalog, tags, permissions, effective, schemas = await asyncio.gather(
            client.get_catalog(catalog_name),
            client.get_tags("catalog", catalog_name),
            client.get_permissions("catalog", catalog_name),
            client.get_effective_permissions("catalog", catalog_name),
            client.list_schemas(catalog_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    # Enforce after gather so we reuse the effective permissions data.
    # AuthorizationError propagates to the centralized handler → 403.html.
    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "catalog",
            catalog_name,
            USE_CATALOG,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )

    # Load sync history for foreign catalogs so the history card has
    # something to render. Managed catalogs never sync, so we skip the
    # DB hit entirely.
    sync_runs: list[Any] = []
    if (
        error is None
        and catalog is not None
        and catalog.get("connection_name")
        and user.get("is_admin", False)
    ):
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None:
            sync_runs = pg_sync_service.list_recent_runs(factory, catalog_name)

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/schemas.html",
        {
            "catalog_name": catalog_name,
            "catalog": catalog,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "can_manage": can_manage,
            "sync_runs": sync_runs,
            "schemas": schemas,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}",
    response_class=HTMLResponse,
)
async def schema_detail(request: Request, catalog_name: str, schema_name: str) -> HTMLResponse:
    """Render metadata for a single schema."""
    client = _get_uc_client(request)
    user = _get_user(request)
    schema: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}"
    try:
        schema, tags, permissions, effective, tables = await asyncio.gather(
            client.get_schema(catalog_name, schema_name),
            client.get_tags("schema", full_name),
            client.get_permissions("schema", full_name),
            client.get_effective_permissions("schema", full_name),
            client.list_tables(catalog_name, schema_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "schema",
            full_name,
            USE_SCHEMA,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/tables.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "schema": schema,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "tables": tables,
            "can_manage": can_manage,
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": None,
        },
    )


@app.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}",
    response_class=HTMLResponse,
)
async def table_detail(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> HTMLResponse:
    """Render metadata and column schema for a single table."""
    client = _get_uc_client(request)
    user = _get_user(request)
    table: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    lineage: dict[str, Any] = {}
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    try:
        table, tags, permissions, effective, lineage = await asyncio.gather(
            client.get_table(catalog_name, schema_name, table_name),
            client.get_tags("table", full_name),
            client.get_permissions("table", full_name),
            client.get_effective_permissions("table", full_name),
            client.get_lineage(full_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "table",
            full_name,
            SELECT,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/table.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "table": table,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "lineage": lineage,
            "can_manage": can_manage,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )


async def _build_notebook_doc_bundle(
    request: Request, path: str
) -> dict[str, Any]:
    """Assemble the ``{cells, dirty, outputs}`` bundle for a notebook.

    Shared by the HTML editor route (which embeds the bundle into the
    page template for first-paint hydration) and the Sprint-68 JSON
    route (which hands the same bundle to the multi-tab editor shell
    when it lazy-loads a second tab without a page reload).

    Args:
        request: Incoming FastAPI request; carries app-state settings
            and session factory.
        path: Relative ``.py`` notebook path under the notebooks dir.

    Returns:
        A dict with ``cells`` (list of ``{id, cell_type, source}``),
        ``dirty`` (bool), and ``outputs`` (list of persisted outputs
        replayed from ``notebook_outputs``).
    """
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    resolved = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=False
    )
    if resolved.is_file():
        document = notebook_doc_service.load_document(resolved, path)
        bundle: dict[str, Any] = {
            "cells": [
                {
                    "id": cell.id,
                    "cell_type": cell.cell_type,
                    "source": cell.source,
                    # Sprint 71 BUG-71-02 fix: round-trip the SQL
                    # cell's optional ``result_var`` through the
                    # bundle so the editor's affordances re-mount
                    # with the user-defined name pre-populated.
                    "result_var": cell.result_var,
                }
                for cell in document.cells
            ],
            "dirty": document.dirty,
        }
    else:
        bundle = {
            "cells": [
                {"id": str(uuid4()), "cell_type": "code", "source": ""},
            ],
            "dirty": True,
        }
    bundle["outputs"] = await asyncio.to_thread(
        notebook_outputs_service.load_outputs_for_path,
        request.app.state.session_factory,
        path,
    )
    return bundle


@app.get("/notebook/editor", response_class=HTMLResponse)
async def notebook_editor_page(request: Request, path: str) -> HTMLResponse:
    """Render the native Phase-12.6 notebook editor (preview).

    The editor opens the ``.py`` (jupytext Percent format) notebook at
    ``path``, relative to the notebooks directory. If the file does
    not exist yet the page renders with a single empty code cell and
    first save materialises the file on disk — mirrors how VSCode's
    Python Interactive window treats a fresh buffer.

    Args:
        request: Incoming FastAPI request.
        path: Relative path under :attr:`Settings.notebooks_dir`.
            Must end in ``.py`` and must not escape the notebooks
            directory.

    Returns:
        Rendered HTML carrying the initial document as a JSON blob
        the Alpine component consumes synchronously on mount.
    """
    initial = await _build_notebook_doc_bundle(request, path)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/notebook_editor.html",
        {
            "notebook_path": path,
            "initial_document": initial,
            "active_page": "notebook_editor",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/api/notebook/doc")
async def api_load_notebook_doc(
    request: Request, path: str
) -> dict[str, Any]:
    """Return the notebook bundle as JSON for the multi-tab editor.

    Sprint-68 companion of the HTML editor route: when the user opens a
    second notebook in a new tab without a full page reload, the shell
    fetches this endpoint to hydrate the tab's Monaco model + replay
    its persisted outputs. Same shape as
    :func:`notebook_editor_page`'s ``initial_document`` — a single
    helper produces both — so the first-paint and lazy-load code paths
    can never drift.

    Args:
        request: Incoming FastAPI request.
        path: Relative ``.py`` notebook path under the notebooks dir.

    Returns:
        ``{"cells": [...], "dirty": bool, "outputs": [...]}``.
    """
    return await _build_notebook_doc_bundle(request, path)


@app.get("/api/notebook/cell-runs")
async def api_list_cell_run_sources(
    request: Request, path: str, cell_id: str, limit: int = 20,
) -> dict[str, Any]:
    """Return the last *limit* per-execute history rows for a cell.

    Sprint 73 — backs the per-cell run-history popover in the editor.
    Each row carries the source the kernel actually saw, the
    lifecycle status, and the start / finish timestamps; the popover
    renders a diff between consecutive ``source`` snapshots and
    offers a one-click re-run that sends the historical source
    straight to the kernel without touching the Monaco buffer.

    Args:
        request: Incoming FastAPI request.
        path: Relative ``.py`` notebook path under the notebooks dir.
        cell_id: Cell UUID to filter on.
        limit: Maximum number of rows to return (newest-first).

    Returns:
        ``{"runs": [{"id", "execution_count", "source", "started_at",
        "finished_at", "status", "kernel_session_id"}, ...]}``
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path, must_exist=False,
    )
    factory = request.app.state.session_factory
    runs = await asyncio.to_thread(
        notebook_outputs_service.list_cell_run_sources,
        factory,
        file_path=path,
        cell_id=cell_id,
        limit=max(1, min(limit, 100)),
    )
    return {"runs": runs}


@app.post("/api/notebook/doc")
async def api_save_notebook_doc(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, str]:
    """Persist a notebook document from the Sprint-58 editor to disk.

    The request body is ``{"path": str, "cells": [{"id", "cell_type",
    "source"}, …]}``. Cells are written in jupytext Percent format
    via :func:`notebook_doc.save_document`; a missing parent directory
    is a :class:`ValidationError` so the editor never silently creates
    arbitrary nested folders.

    Args:
        request: Incoming FastAPI request. The CSRF middleware already
            checks the ``X-CSRF-Token`` header before the handler runs.
        body: The parsed JSON payload.

    Returns:
        ``{"path": str, "status": "saved"}``.

    Raises:
        ValidationError: On bad payload shape, traversal attempt, or
            non-existent parent directory.
    """
    settings: Settings = request.app.state.settings
    path = body.get("path")
    raw_cells = body.get("cells")
    if not isinstance(path, str) or not isinstance(raw_cells, list):
        raise ValidationError("payload must carry 'path': str and 'cells': list")
    cells: list[notebook_doc_service.NotebookCell] = []
    for idx, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise ValidationError(f"cell {idx} must be an object")
        cell_id = raw.get("id")
        cell_type = raw.get("cell_type")
        source = raw.get("source")
        # Sprint 71 BUG-71-02 fix: accept ``sql`` alongside ``code`` /
        # ``markdown`` and read the optional ``result_var`` field so
        # the post-jupytext rewrite can put the segment back on disk.
        result_var = raw.get("result_var")
        if not isinstance(cell_id, str) or not cell_id:
            raise ValidationError(f"cell {idx} missing 'id'")
        if cell_type not in ("code", "markdown", "sql"):
            raise ValidationError(f"cell {idx} has unsupported cell_type {cell_type!r}")
        if not isinstance(source, str):
            raise ValidationError(f"cell {idx} 'source' must be a string")
        if result_var is not None and not isinstance(result_var, str):
            raise ValidationError(
                f"cell {idx} 'result_var' must be a string or null",
            )
        cells.append(
            notebook_doc_service.NotebookCell(
                id=cell_id,
                cell_type=cell_type,
                source=source,
                result_var=result_var if cell_type == "sql" else None,
            )
        )
    resolved = notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path, must_exist=False
    )
    notebook_doc_service.save_document(resolved, cells)
    await _audit(request, "notebook.saved", f"notebook:{path}", f"cells={len(cells)}")
    return {"path": path, "status": "saved"}


async def _resolve_sql_approved_tables(
    websocket: WebSocket,
    settings: Settings,
    user: UserInfo,
    query: str,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Parse a SQL string and return ``(approved_tables, error_or_none)``.

    Sprint 71 — shared shape with ``POST /api/sql/execute``: parse via
    :func:`prepare_sql`, look up every referenced 3-part name in
    soyuz-catalog, and run :func:`check_privilege` for ``SELECT`` so
    the kernel never sees a query the caller does not have rights to
    run.  Returns the ``approved_tables`` map on success, or an
    ``error`` content dict shaped like an iopub ``error`` message
    (``ename`` / ``evalue`` / ``traceback``) on any failure so the WS
    handler can ship a synthetic kernel_msg straight to the cell's
    output zone.

    Args:
        websocket: WebSocket whose ``app.state`` holds settings.
        settings: Application settings (needed for ``sql.enabled``).
        user: Authenticated user from the JWT cookie.
        query: SQL source as typed in the cell.

    Returns:
        ``(approved_tables, None)`` on success — the dict maps every
        ``catalog.schema.table`` reference to its Delta storage
        location.  ``({}, error_dict)`` on failure (parse error,
        unknown table, missing storage location, denied privilege).
    """
    from pointlessql.exceptions import (
        AuthorizationError,
        CatalogNotFoundError,
        SQLExecutionError,
    )
    from pointlessql.pql.sql_parser import SQLParseError, prepare_sql

    try:
        prepared = prepare_sql(query)
    except SQLParseError as exc:
        return {}, {
            "ename": "SQLParseError",
            "evalue": str(exc),
            "traceback": [],
        }

    client = UnityCatalogClient.for_principal(settings, user["email"])
    email = user["email"]
    is_admin = bool(user.get("is_admin", False))
    approved: dict[str, str] = {}
    try:
        for full_name in prepared.refs:
            parts = full_name.split(".")
            if len(parts) != 3:
                return {}, {
                    "ename": "SQLExecutionError",
                    "evalue": f"Internal error: expected 3-part name, got {full_name!r}.",
                    "traceback": [],
                }
            table_info = await client.get_table(parts[0], parts[1], parts[2])
            if not table_info:
                return {}, {
                    "ename": "CatalogNotFoundError",
                    "evalue": f"Table not found: {full_name!r}",
                    "traceback": [],
                }
            storage_location = table_info.get("storage_location")
            if not isinstance(storage_location, str) or not storage_location:
                return {}, {
                    "ename": "CatalogNotFoundError",
                    "evalue": (
                        f"Table {full_name!r} has no storage_location on soyuz-catalog."
                    ),
                    "traceback": [],
                }
            await check_privilege(client, email, is_admin, "table", full_name, SELECT)
            approved[full_name] = storage_location
    except AuthorizationError as exc:
        return {}, {
            "ename": "AuthorizationError",
            "evalue": str(exc),
            "traceback": [],
        }
    except (CatalogNotFoundError, SQLExecutionError) as exc:
        return {}, {
            "ename": type(exc).__name__,
            "evalue": str(exc),
            "traceback": [],
        }
    finally:
        await client.aclose()

    return approved, None


@app.websocket("/ws/notebook/kernel")
async def ws_notebook_kernel(websocket: WebSocket, path: str) -> None:
    """Bidirectional ZMQ↔WS proxy for the native-editor kernel.

    Sprint 59 endpoint. WebSocket upgrades bypass the HTTP auth
    middleware, so we pull the ``pql_session`` cookie manually and
    decode the JWT via :func:`auth_service.get_current_user`. A
    client frame is a JSON object with ``type`` in
    ``{"execute", "interrupt", "restart"}``; the server responds
    with ``type`` in ``{"hello", "ack", "restarted", "kernel_msg",
    "error"}``.

    One WS connection maps to one subscriber on the shared kernel;
    a second tab for the same ``(user, notebook_path)`` pair gets a
    second subscription on the same subprocess — ADR-0001 "kernel
    per notebook path" decision.

    Args:
        websocket: Incoming FastAPI WebSocket.
        path: Relative notebook path (query param) — validated with
            the same traversal guard the HTTP save endpoint uses.
    """
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if not token:
        await websocket.close(code=4401)
        return

    factory = websocket.app.state.session_factory
    settings: Settings = websocket.app.state.settings
    user = auth_service.get_current_user(
        factory,
        token,
        settings.auth.secret_key,
        previous_key=settings.auth.secret_key_previous,
    )
    if user is None:
        await websocket.close(code=4401)
        return

    try:
        notebook_doc_service.resolve_py_notebook_path(
            settings.jupyter.notebooks_dir.resolve(),
            path,
            must_exist=False,
        )
    except ValidationError:
        await websocket.close(code=4400)
        return

    await websocket.accept()

    registry: kernel_session_service.KernelRegistry = (
        websocket.app.state.kernel_registry
    )
    try:
        session = await registry.get_or_start(user["id"], user["email"], path)
    except Exception as exc:  # noqa: BLE001 — kernel start can fail for many reasons
        logger.exception("kernel start failed for %s notebook=%s", user["email"], path)
        await websocket.send_json(
            {"type": "error", "message": f"kernel start failed: {exc}"}
        )
        await websocket.close(code=1011)
        return

    subscription = session.subscribe()
    await websocket.send_json(
        {
            "type": "hello",
            "kernel_session_id": session.session_id,
            "notebook_path": path,
        }
    )

    # Sprint 60: per-(cell_id, kernel_session_id) output counter.
    # A new `execute` on a cell wipes the previous outputs (both in
    # memory and in the DB via ``clear_cell``) and resets its
    # counter to 0, so persisted rows always stay contiguous.
    output_counters: dict[tuple[str, str], int] = {}
    # Sprint 73: pending run-source ids keyed by ``(cell_id,
    # kernel_session_id)``.  ``record_cell_run_start`` returns the
    # autoincrement id on execute; the matching execute_reply pops
    # the id and calls ``record_cell_run_finish`` to stamp status +
    # finish + execution_count.  Cleared on WS disconnect / restart
    # so a dropped reply never leaks rows.
    pending_run_sources: dict[tuple[str, str], int] = {}

    # Sprint 62: ``__pql_``-prefixed cell IDs are reserved for the
    # editor's internal introspects (Variable Explorer namespace
    # scan, future autocomplete helpers).  Skipping persistence on
    # these keeps the ``notebook_outputs`` table free of silent-
    # execute rows that never surface in the UI.
    def _is_internal_cell(cell_id: str | None) -> bool:
        return bool(cell_id) and cell_id.startswith("__pql_")

    async def _persist_kernel_msg(msg: kernel_session_service.KernelMessage) -> None:
        if not msg.cell_id or _is_internal_cell(msg.cell_id):
            return
        if not notebook_outputs_service.is_persistable(msg.msg_type):
            return
        key = (msg.cell_id, session.session_id)
        idx = output_counters.get(key, 0)
        output_counters[key] = idx + 1
        await asyncio.to_thread(
            notebook_outputs_service.append_output,
            factory,
            file_path=path,
            cell_id=msg.cell_id,
            kernel_session_id=session.session_id,
            output_index=idx,
            msg_type=msg.msg_type,
            content=msg.content,
            metadata=msg.metadata or None,
        )

    async def _handle_shell_lifecycle(
        msg: kernel_session_service.KernelMessage,
    ) -> None:
        if msg.msg_type != "execute_reply" or not msg.cell_id:
            return
        if _is_internal_cell(msg.cell_id):
            return
        raw_status = msg.content.get("status", "ok")
        status: str = raw_status if isinstance(raw_status, str) else "ok"
        execution_count = msg.content.get("execution_count")
        ec_int = execution_count if isinstance(execution_count, int) else None
        await asyncio.to_thread(
            notebook_outputs_service.upsert_cell_run,
            factory,
            file_path=path,
            cell_id=msg.cell_id,
            kernel_session_id=session.session_id,
            status=status,
            execution_count=ec_int,
            finished=True,
        )
        # Sprint 73: stamp the per-execute history row this reply
        # belongs to.  Lookup is by (cell_id, kernel_session_id) —
        # the kernel serialises execute_requests so the queued
        # reply matches the most recent start in flight for that
        # key.  Pop on success so a bug in the kernel that emits
        # two replies for one request does not double-stamp.
        source_id = pending_run_sources.pop(
            (msg.cell_id, session.session_id), None,
        )
        if source_id is not None:
            await asyncio.to_thread(
                notebook_outputs_service.record_cell_run_finish,
                factory,
                source_id=source_id,
                status=status,
                execution_count=ec_int,
                finished_at=datetime.now(UTC),
            )

    async def _forward(channel: str) -> None:
        queue = subscription.iopub if channel == "iopub" else subscription.shell
        try:
            async for msg in kernel_session_service.drain(queue):
                if channel == "iopub":
                    await _persist_kernel_msg(msg)
                else:
                    await _handle_shell_lifecycle(msg)
                payload = {
                    "type": "kernel_msg",
                    "channel": msg.channel,
                    "msg_type": msg.msg_type,
                    "cell_id": msg.cell_id,
                    "parent_msg_id": msg.parent_msg_id,
                    "content": jsonable_encoder(msg.content),
                    "metadata": jsonable_encoder(msg.metadata),
                }
                await websocket.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            return

    forward_tasks = [
        asyncio.create_task(_forward("iopub"), name="ws-kernel-iopub"),
        asyncio.create_task(_forward("shell"), name="ws-kernel-shell"),
    ]

    async def _wipe_cell_for_new_execute(cell_id: str, source: str) -> None:
        """Reset persistence + counter state before a fresh execute.

        Sprint 71 factored out of the ``execute`` branch so the new
        ``execute_sql`` branch can share the same prelude (clear
        previous outputs, drop the per-cell index, mark the run as
        ``running``).  Sprint 73 extends it to also insert a per-
        execute history row via ``record_cell_run_start`` and stash
        the returned id in ``pending_run_sources`` so the matching
        execute_reply can stamp the finish.  Internal
        ``__pql_``-prefixed cells stay unpersisted, so this is a
        no-op for them.

        Args:
            cell_id: Cell UUID.
            source: Source the kernel will execute (raw Python for
                ``execute``, wrapped ``__pql_sql_run(...)`` snippet
                for ``execute_sql``).  Stored verbatim in the
                history row.
        """
        if _is_internal_cell(cell_id):
            return
        await asyncio.to_thread(
            notebook_outputs_service.clear_cell,
            factory, file_path=path, cell_id=cell_id,
        )
        output_counters.pop((cell_id, session.session_id), None)
        # Drop any orphan from a dropped reply on the prior run for
        # this key so the new start doesn't double-stamp the wrong id
        # when the next reply arrives.
        pending_run_sources.pop((cell_id, session.session_id), None)
        await asyncio.to_thread(
            notebook_outputs_service.upsert_cell_run,
            factory,
            file_path=path,
            cell_id=cell_id,
            kernel_session_id=session.session_id,
            status="running",
        )
        source_id = await asyncio.to_thread(
            notebook_outputs_service.record_cell_run_start,
            factory,
            file_path=path,
            cell_id=cell_id,
            kernel_session_id=session.session_id,
            source=source,
            started_at=datetime.now(UTC),
        )
        pending_run_sources[(cell_id, session.session_id)] = source_id

    try:
        while True:
            frame = await websocket.receive_json()
            ftype = frame.get("type")
            if ftype == "execute":
                code = frame.get("code", "")
                cell_id = frame.get("cell_id", "")
                if not isinstance(code, str) or not isinstance(cell_id, str):
                    await websocket.send_json(
                        {"type": "error", "message": "execute needs string code + cell_id"}
                    )
                    continue
                await _wipe_cell_for_new_execute(cell_id, code)
                msg_id = await session.execute(code, cell_id)
                await websocket.send_json(
                    {"type": "ack", "msg_id": msg_id, "cell_id": cell_id}
                )
            elif ftype == "execute_sql":
                # Sprint 71: SQL cell.  Parse + privilege-check the
                # query route-side (mirrors ``/api/sql/execute``), then
                # send a wrapped ``__pql_sql_run(...)`` snippet to the
                # kernel for execution.  The kernel-side helper builds
                # a pandas DataFrame from the result, optionally binds
                # it under ``result_var`` so Variable Explorer surfaces
                # it, and ``display(df)`` so the existing rich-mime
                # path renders the table inline.
                source = frame.get("source", "")
                cell_id = frame.get("cell_id", "")
                result_var = frame.get("result_var")
                if (
                    not isinstance(source, str)
                    or not isinstance(cell_id, str)
                    or (result_var is not None and not isinstance(result_var, str))
                ):
                    await websocket.send_json({
                        "type": "error",
                        "message": (
                            "execute_sql needs string source + cell_id "
                            "(and optional string result_var)"
                        ),
                    })
                    continue
                if not settings.sql.enabled:
                    await websocket.send_json({
                        "type": "kernel_msg",
                        "channel": "iopub",
                        "msg_type": "error",
                        "cell_id": cell_id,
                        "parent_msg_id": None,
                        "content": {
                            "ename": "SQLDisabled",
                            "evalue": "The SQL editor is disabled on this deployment.",
                            "traceback": [],
                        },
                        "metadata": {},
                    })
                    continue
                approved, err = await _resolve_sql_approved_tables(
                    websocket, settings, user, source,
                )
                if err is not None:
                    await websocket.send_json({
                        "type": "kernel_msg",
                        "channel": "iopub",
                        "msg_type": "error",
                        "cell_id": cell_id,
                        "parent_msg_id": None,
                        "content": err,
                        "metadata": {},
                    })
                    continue
                wrapped = (
                    "__pql_sql_run("
                    f"{json.dumps(source)}, "
                    f"approved_tables={json.dumps(approved)}, "
                    f"result_var={json.dumps(result_var) if result_var else 'None'}, "
                    f"max_rows={int(settings.sql.max_rows)}"
                    ")"
                )
                await _wipe_cell_for_new_execute(cell_id, wrapped)
                msg_id = await session.execute(wrapped, cell_id)
                await websocket.send_json(
                    {"type": "ack", "msg_id": msg_id, "cell_id": cell_id}
                )
            elif ftype == "interrupt":
                await session.interrupt()
                await websocket.send_json({"type": "interrupted"})
            elif ftype == "restart":
                # Purge the outgoing session's rows *before* the
                # kernel starts handing out a new session_id.
                await asyncio.to_thread(
                    notebook_outputs_service.clear_session,
                    factory,
                    file_path=path,
                    kernel_session_id=session.session_id,
                )
                output_counters.clear()
                pending_run_sources.clear()
                await session.restart()
                await websocket.send_json(
                    {
                        "type": "restarted",
                        "kernel_session_id": session.session_id,
                    }
                )
            elif ftype == "clear_cell":
                cell_id = frame.get("cell_id", "")
                if isinstance(cell_id, str) and cell_id:
                    await asyncio.to_thread(
                        notebook_outputs_service.clear_cell,
                        factory, file_path=path, cell_id=cell_id,
                    )
                    output_counters.pop((cell_id, session.session_id), None)
                await websocket.send_json({"type": "cell_cleared", "cell_id": cell_id})
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"unknown frame type {ftype!r}"}
                )
    except WebSocketDisconnect:
        pass
    finally:
        for task in forward_tasks:
            task.cancel()
        for task in forward_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        session.unsubscribe(subscription)


@app.websocket("/ws/notebook/lsp")
async def ws_notebook_lsp(websocket: WebSocket, path: str) -> None:
    """Bidirectional LSP JSON-RPC proxy for the notebook editor.

    Sprint 61 endpoint.  Mirrors the Sprint-59 kernel WS: manual
    cookie-based auth (WS upgrades bypass HTTP middleware), same
    traversal guard for the notebook path.  One pyright-langserver
    subprocess is spawned per WS connection and torn down on
    disconnect — per-tab isolation keeps the routing trivial.

    The WS frames carry raw LSP JSON-RPC messages (request /
    response / notification) verbatim.  The server is a pure
    framing proxy: it adds the ``Content-Length`` header on the
    way in, strips it on the way out.  Client code can therefore
    use any off-the-shelf LSP client or (in our case) a hand-
    rolled minimal one on top of Monaco's provider APIs.

    Args:
        websocket: Incoming FastAPI WebSocket.
        path: Relative notebook path (query param). Validated with
            the same traversal guard as the save endpoint.
    """
    token = websocket.cookies.get(auth_service.COOKIE_NAME)
    if not token:
        await websocket.close(code=4401)
        return

    factory = websocket.app.state.session_factory
    settings: Settings = websocket.app.state.settings
    user = auth_service.get_current_user(
        factory,
        token,
        settings.auth.secret_key,
        previous_key=settings.auth.secret_key_previous,
    )
    if user is None:
        await websocket.close(code=4401)
        return

    try:
        notebook_doc_service.resolve_py_notebook_path(
            settings.jupyter.notebooks_dir.resolve(),
            path,
            must_exist=False,
        )
    except ValidationError:
        await websocket.close(code=4400)
        return

    if pyright_bridge_service.find_pyright_langserver() is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()

    async def _forward_from_pyright(message: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(message))
        except WebSocketDisconnect:
            return

    session = pyright_bridge_service.PyrightSession(_forward_from_pyright)
    try:
        await session.start()
    except Exception as exc:  # noqa: BLE001 — langserver spawn can fail in several ways
        logger.exception("pyright-langserver start failed for %s", user["email"])
        await websocket.send_json({
            "type": "error",
            "message": f"pyright start failed: {exc}",
        })
        await websocket.close(code=1011)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            await session.send(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await session.shutdown()


@app.get("/api/notebooks/inspect")
async def api_inspect_notebook(request: Request, path: str) -> list[dict[str, Any]]:
    """Return a notebook's declared Papermill parameters.

    Introspects the ``parameters``-tagged cell via
    :func:`papermill.inspect_notebook` and returns one entry per
    declared parameter. The create-job modal uses this to render a
    typed form instead of the raw JSON textarea introduced in
    Sprint 24.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path, resolved under
            :attr:`Settings.notebooks_dir`. Must not escape the
            directory — uses the same validator as the executor.

    Returns:
        A list of ``{"name", "default", "inferred_type", "help"}``
        dicts. ``default`` is the literal default string Papermill
        extracts (the client coerces it per ``inferred_type``).
    """
    import papermill  # type: ignore[import-untyped]

    _require_admin(request)
    settings: Settings = request.app.state.settings
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path
    )
    raw = papermill.inspect_notebook(str(resolved))
    out: list[dict[str, Any]] = []
    for name, meta in raw.items():
        meta_dict: dict[str, Any] = meta
        out.append(
            {
                "name": name,
                "default": meta_dict.get("default"),
                "inferred_type": meta_dict.get("inferred_type_name") or "str",
                "help": meta_dict.get("help", ""),
            }
        )
    return out


@app.get("/api/notebooks/tree")
async def api_notebooks_tree(request: Request) -> list[dict[str, Any]]:
    """Return a nested listing of the notebooks workspace directory.

    Admin-only, matching the inspect + upload routes in this family.
    Each notebook leaf carries a ``parameters_tagged`` flag so the
    workspace UI can hint which files will render a typed form in
    the create-job modal.

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        A list of directory and notebook nodes. See
        :func:`pointlessql.services.notebook_workspace.list_workspace_tree`
        for the shape of each node.
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    return notebook_workspace_service.list_workspace_tree(settings.jupyter.notebooks_dir.resolve())


@app.post("/api/notebooks/upload")
async def api_upload_notebook(
    request: Request,
    file: UploadFile = File(...),
    target_path: str = Form(...),
    overwrite: bool = Form(False),
) -> dict[str, str]:
    """Upload an ``.ipynb`` file into the notebooks workspace.

    Admin-only. The ``target_path`` is resolved under
    :attr:`Settings.notebooks_dir` with the same traversal guard the
    executor uses (via
    :func:`pointlessql.services.notebook_workspace.resolve_upload_target`).
    The upload payload must be a well-formed JSON notebook; the body
    is parsed before the file hits disk so a corrupt upload never
    leaves a half-written file in the workspace. Writes are atomic
    via a ``.tmp`` sidecar + :func:`os.replace`.

    Args:
        request: Incoming FastAPI request; admin-only.
        file: The multipart upload. ``file.filename`` must end in
            ``.ipynb``.
        target_path: Relative path under the notebooks directory
            where the upload should land.
        overwrite: When ``True``, an existing file at ``target_path``
            is replaced. When ``False`` (the default), attempting to
            upload over an existing file raises
            :class:`~pointlessql.exceptions.ValidationError`.

    Returns:
        A dict with ``path`` (the relative path the file was written
        to) and ``status`` (``"created"`` or ``"overwritten"``).

    Raises:
        ValidationError: On any of the upload guards (bad filename,
            path traversal, malformed JSON body, existing file
            without ``overwrite=True``). ``AuthorizationError`` is
            raised out of ``_require_admin`` for non-admin callers
            and surfaced as 403 by the centralized error handler.
    """
    import os

    _require_admin(request)
    settings: Settings = request.app.state.settings

    filename = file.filename or ""
    if not filename.endswith(".ipynb"):
        raise ValidationError(f"uploaded file must have an .ipynb extension: {filename!r}")

    resolved = notebook_workspace_service.resolve_upload_target(
        settings.jupyter.notebooks_dir.resolve(), target_path
    )

    raw = await file.read()
    try:
        json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"uploaded file is not valid JSON: {exc}") from exc

    existed = resolved.exists()
    if existed and not overwrite:
        raise ValidationError(
            f"file already exists at {target_path!r}; pass overwrite=true to replace"
        )

    tmp_path = resolved.with_suffix(resolved.suffix + ".tmp")
    tmp_path.write_bytes(raw)
    os.replace(tmp_path, resolved)

    await _audit(
        request,
        action="notebook.upload",
        target=target_path,
        detail=f"overwrite={overwrite}",
    )
    logger.info(
        "notebook uploaded to %s (overwrite=%s, existed=%s)",
        target_path,
        overwrite,
        existed,
    )
    return {
        "path": target_path,
        "status": "overwritten" if existed else "created",
    }


@app.post("/api/notebooks/create")
async def api_create_notebook(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, str]:
    """Create an empty ``.py`` notebook in the workspace (admin-only).

    Sprint 67 sidebar "New…" action. Writes a zero-byte file at
    ``body["path"]`` — the editor's open handler at
    :func:`notebook_editor_page` already renders an empty cell and
    materialises cell markers on first save when it encounters a
    zero-byte file, so there is no template content to maintain here.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with a required ``path`` key naming the
            relative ``.py`` path to create.

    Returns:
        ``{"path": "...", "status": "created"}``.

    Raises:
        ValidationError: On traversal, wrong suffix, missing parent
            directory, or when a file already exists at ``path``.
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    raw = body.get("path")
    if not isinstance(raw, str):
        raise ValidationError("create request requires a 'path' string")
    notebook_workspace_service.create_empty_notebook(
        settings.jupyter.notebooks_dir.resolve(), raw
    )
    await _audit(request, action="notebook.create", target=raw)
    logger.info("notebook created at %s", raw)
    return {"path": raw, "status": "created"}


@app.patch("/api/notebooks/rename")
async def api_rename_notebook(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, str]:
    """Rename an existing notebook and re-key its replay cache.

    Sprint 67 sidebar rename action. The filesystem move goes through
    :func:`notebook_workspace.rename_notebook`; the replay cache in
    ``notebook_outputs`` + ``notebook_cell_runs`` is re-keyed by
    :func:`notebook_outputs.rename_path` so prior run artefacts
    survive the rename — a UX property a user expects when the only
    thing they changed was the file's name.

    Args:
        request: Incoming FastAPI request; admin-only.
        body: JSON body with required ``old_path`` and ``new_path``
            keys, both relative to the notebooks directory.

    Returns:
        ``{"old_path": "...", "new_path": "...", "status": "renamed"}``.

    Raises:
        ValidationError: On traversal / suffix violations, when the
            source is missing, or when the destination already
            exists.
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    old_raw = body.get("old_path")
    new_raw = body.get("new_path")
    if not isinstance(old_raw, str) or not isinstance(new_raw, str):
        raise ValidationError("rename request requires 'old_path' and 'new_path' strings")
    notebook_workspace_service.rename_notebook(
        settings.jupyter.notebooks_dir.resolve(), old_raw, new_raw
    )
    await asyncio.to_thread(
        notebook_outputs_service.rename_path,
        request.app.state.session_factory,
        old_raw,
        new_raw,
    )
    await _audit(
        request,
        action="notebook.rename",
        target=old_raw,
        detail=f"new_path={new_raw}",
    )
    logger.info("notebook renamed from %s to %s", old_raw, new_raw)
    return {"old_path": old_raw, "new_path": new_raw, "status": "renamed"}


@app.delete("/api/notebooks")
async def api_delete_notebook(request: Request, path: str) -> dict[str, str]:
    """Delete a notebook and cascade its replay cache (admin-only).

    Sprint 67 sidebar delete action. ``path`` is taken as a query
    parameter rather than a ``{path:path}`` URL segment to sidestep
    the regex-vs-slash ambiguity that nested notebook paths
    (``sub/dir/foo.py``) introduce. The filesystem ``unlink`` happens
    first; the replay-cache cascade via :func:`clear_path` happens
    after and can tolerate "no rows matched" for a notebook that was
    never executed.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path to delete.

    Returns:
        ``{"path": "...", "status": "deleted"}``.  The ``ValidationError``
        contract of :func:`notebook_workspace.delete_notebook` applies
        — traversal / suffix violations and already-missing files
        raise.
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    notebook_workspace_service.delete_notebook(
        settings.jupyter.notebooks_dir.resolve(), path
    )
    await asyncio.to_thread(
        notebook_outputs_service.clear_path,
        request.app.state.session_factory,
        path,
    )
    await _audit(request, action="notebook.delete", target=path)
    logger.info("notebook deleted at %s", path)
    return {"path": path, "status": "deleted"}


@app.get("/notebooks/workspace", response_class=HTMLResponse)
async def notebooks_workspace_page(request: Request) -> HTMLResponse:
    """Render the Sprint 27 workspace file browser (admin-only).

    The page pairs a notebook-tree sidebar (served by
    ``/api/notebooks/tree``) with an upload card. Tree-leaf
    *Schedule…* buttons navigate to
    ``/jobs?prefill_kind=papermill&prefill_notebook_path=<path>``;
    the create-job modal reads those query params on load and
    pre-fills itself.

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        The rendered ``pages/notebooks_workspace.html`` template.
    """
    _require_admin(request)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/notebooks_workspace.html",
        {
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Federation: Connections --


@app.get("/api/connections")
async def api_list_connections(request: Request) -> list[dict[str, object]]:
    """Return all connections (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_connections()


@app.post("/api/connections")
async def api_create_connection(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_connection(body)
    await _audit(request, "create_connection", f"connection:{body.get('name', '?')}")
    return result


@app.get("/api/connections/{name}")
async def api_get_connection(request: Request, name: str) -> dict[str, object]:
    """Return a single connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_connection(name)


@app.patch("/api/connections/{name}")
async def api_update_connection(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update a connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_connection(name, body)
    await _audit(request, "update_connection", f"connection:{name}", json.dumps(body))
    return result


@app.delete("/api/connections/{name}")
async def api_delete_connection(request: Request, name: str) -> dict[str, str]:
    """Delete a connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_connection(name)
    await _audit(request, "delete_connection", f"connection:{name}")
    return {"status": "deleted"}


# -- Federation: External Locations --


@app.get("/api/external-locations")
async def api_list_external_locations(request: Request) -> list[dict[str, object]]:
    """Return all external locations (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_external_locations()


@app.post("/api/external-locations")
async def api_create_external_location(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_external_location(body)
    await _audit(request, "create_ext_location", f"ext_location:{body.get('name', '?')}")
    return result


@app.get("/api/external-locations/{name}")
async def api_get_external_location(request: Request, name: str) -> dict[str, object]:
    """Return a single external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_external_location(name)


@app.patch("/api/external-locations/{name}")
async def api_update_external_location(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update an external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_external_location(name, body)
    await _audit(request, "update_ext_location", f"ext_location:{name}", json.dumps(body))
    return result


@app.delete("/api/external-locations/{name}")
async def api_delete_external_location(request: Request, name: str) -> dict[str, str]:
    """Delete an external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_external_location(name)
    await _audit(request, "delete_ext_location", f"ext_location:{name}")
    return {"status": "deleted"}


# -- Federation: Credentials --


@app.get("/api/credentials")
async def api_list_credentials(request: Request) -> list[dict[str, object]]:
    """Return all credentials (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_credentials()


@app.post("/api/credentials")
async def api_create_credential(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_credential(body)
    await _audit(request, "create_credential", f"credential:{body.get('name', '?')}")
    return result


@app.get("/api/credentials/{name}")
async def api_get_credential(request: Request, name: str) -> dict[str, object]:
    """Return a single credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_credential(name)


@app.patch("/api/credentials/{name}")
async def api_update_credential(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update a credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_credential(name, body)
    await _audit(request, "update_credential", f"credential:{name}", json.dumps(body))
    return result


@app.delete("/api/credentials/{name}")
async def api_delete_credential(request: Request, name: str) -> dict[str, str]:
    """Delete a credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_credential(name)
    await _audit(request, "delete_credential", f"credential:{name}")
    return {"status": "deleted"}


# -- Federation: HTML pages --


@app.get("/connections", response_class=HTMLResponse)
async def connections_index(request: Request) -> HTMLResponse:
    """List all connections (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    connections: list[dict[str, Any]] = []
    error: str | None = None
    try:
        connections = await client.list_connections()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connections.html",
        {
            "connections": connections,
            "error": error,
            "active_page": "connections",
            "list_page": True,
        },
    )


@app.get("/connections/{name}", response_class=HTMLResponse)
async def connection_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    connection: dict[str, Any] | None = None
    error: str | None = None
    try:
        connection = await client.get_connection(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connection.html",
        {"connection": connection, "name": name, "error": error, "active_page": "connections"},
    )


@app.get("/external-locations", response_class=HTMLResponse)
async def external_locations_index(request: Request) -> HTMLResponse:
    """List all external locations (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    locations: list[dict[str, Any]] = []
    error: str | None = None
    try:
        locations = await client.list_external_locations()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_locations.html",
        {
            "locations": locations,
            "error": error,
            "active_page": "external_locations",
            "list_page": True,
        },
    )


@app.get("/external-locations/{name}", response_class=HTMLResponse)
async def external_location_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    location: dict[str, Any] | None = None
    error: str | None = None
    try:
        location = await client.get_external_location(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_location.html",
        {"location": location, "name": name, "error": error, "active_page": "external_locations"},
    )


@app.get("/credentials", response_class=HTMLResponse)
async def credentials_index(request: Request) -> HTMLResponse:
    """List all credentials (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    credentials: list[dict[str, Any]] = []
    error: str | None = None
    try:
        credentials = await client.list_credentials()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credentials.html",
        {
            "credentials": credentials,
            "error": error,
            "active_page": "credentials",
            "list_page": True,
        },
    )


@app.get("/credentials/{name}", response_class=HTMLResponse)
async def credential_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    credential: dict[str, Any] | None = None
    error: str | None = None
    try:
        credential = await client.get_credential(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credential.html",
        {"credential": credential, "name": name, "error": error, "active_page": "credentials"},
    )


# -- Jobs / scheduler --


_JOB_REGISTRY = scheduler_service.build_default_registry()


def _serialize_job(job: Any, last_run: Any = None) -> dict[str, Any]:
    """Render a :class:`Job` ORM row for JSON responses.

    Pulled out into a helper so both the list and the detail route
    emit the same shape; the helper assumes the ORM row has been
    detached from its session or the caller still holds the session
    open (we never serialize half-loaded jobs).

    When *last_run* is supplied (typically from
    :func:`_latest_run_per_job`), the ``last_run_*`` fields are
    populated from it; otherwise they are ``None``. List endpoints
    thread the latest-run map in, detail/mutation endpoints do not —
    the keys are always present so clients never need to branch on
    their existence.

    Args:
        job: Detached :class:`~pointlessql.models.Job` ORM row.
        last_run: Optional latest :class:`~pointlessql.models.JobRun`
            for this job, used to populate ``last_run_*`` fields.

    Returns:
        A dict with the canonical job shape plus ``last_run_status``,
        ``last_run_at``, and ``last_run_duration_s``.
    """
    last_status: str | None = None
    last_at: str | None = None
    last_duration: float | None = None
    if last_run is not None:
        last_status = last_run.status
        last_at = last_run.started_at.isoformat() if last_run.started_at else None
        if last_run.started_at and last_run.finished_at:
            last_duration = (last_run.finished_at - last_run.started_at).total_seconds()
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "run_as_user_id": job.run_as_user_id,
        "kind": job.kind,
        "config": json.loads(job.config or "{}"),
        "is_paused": job.is_paused,
        "max_parallel_runs": job.max_parallel_runs,
        "on_failure_url": job.on_failure_url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "last_run_status": last_status,
        "last_run_at": last_at,
        "last_run_duration_s": last_duration,
    }


def _latest_run_per_job(session: Any, job_ids: list[int]) -> dict[int, Any]:
    """Fetch the most recent :class:`JobRun` row for each of *job_ids*.

    One round-trip: a ``group_by(job_id)`` subquery pulls the max
    ``started_at`` per job, then the outer select joins back to
    ``job_runs`` on both columns to grab the full row. Portable
    across SQLite and Postgres — no window functions, no lateral
    joins — and rides the existing ``(job_id, started_at)`` index
    declared on :class:`~pointlessql.models.JobRun`.

    Args:
        session: An open SQLAlchemy session.
        job_ids: The jobs whose latest run should be fetched. May be
            empty, in which case an empty dict is returned without
            issuing a query.

    Returns:
        A mapping from ``job_id`` to its most recent
        :class:`~pointlessql.models.JobRun`. Jobs with no runs yet are
        simply absent from the dict.
    """
    if not job_ids:
        return {}
    from sqlalchemy import and_, func
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    latest_sq = (
        _select(
            JobRunModel.job_id.label("job_id"),
            func.max(JobRunModel.started_at).label("last_at"),
        )
        .where(JobRunModel.job_id.in_(job_ids))
        .group_by(JobRunModel.job_id)
        .subquery()
    )
    stmt = _select(JobRunModel).join(
        latest_sq,
        and_(
            JobRunModel.job_id == latest_sq.c.job_id,
            JobRunModel.started_at == latest_sq.c.last_at,
        ),
    )
    out: dict[int, Any] = {}
    for run in session.scalars(stmt).all():
        # Two runs with identical started_at timestamps would both
        # satisfy the join; pick the higher-id one so a single row
        # wins deterministically.
        prev = out.get(run.job_id)
        if prev is None or run.id > prev.id:
            out[run.job_id] = run
    for run in out.values():
        session.expunge(run)
    return out


def _serialize_task(task: Any) -> dict[str, Any]:
    """Render a :class:`JobTask` ORM row for JSON responses."""
    return {
        "id": task.id,
        "job_id": task.job_id,
        "name": task.name,
        "kind": task.kind,
        "config": json.loads(task.config or "{}"),
        "depends_on": json.loads(task.depends_on or "[]"),
        "max_retries": task.max_retries,
        "retry_backoff_seconds": task.retry_backoff_seconds,
    }


def _serialize_task_run(tr: Any) -> dict[str, Any]:
    """Render a :class:`TaskRun` ORM row for JSON responses."""
    return {
        "id": tr.id,
        "job_run_id": tr.job_run_id,
        "task_id": tr.task_id,
        "status": tr.status,
        "started_at": tr.started_at.isoformat() if tr.started_at else None,
        "finished_at": tr.finished_at.isoformat() if tr.finished_at else None,
        "attempts": tr.attempts,
        "error": tr.error,
    }


def _serialize_run(run: Any) -> dict[str, Any]:
    """Render a :class:`JobRun` ORM row for JSON responses."""
    duration: float | None = None
    if run.started_at and run.finished_at:
        duration = (run.finished_at - run.started_at).total_seconds()
    return {
        "id": run.id,
        "job_id": run.job_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "trigger": run.trigger,
        "error": run.error,
        "duration_seconds": duration,
    }


def _load_job_or_404(request: Request, job_id: int) -> Any:
    """Fetch a :class:`Job` with ownership-aware visibility rules.

    Admins see every job; non-admins see only jobs whose
    ``run_as_user_id`` matches their user id. A missing or hidden job
    surfaces as :class:`CatalogNotFoundError` so the centralized
    error handler renders 404 consistently.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        job = session.get(JobModel, job_id)
        if job is None:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        if not user.get("is_admin") and job.run_as_user_id != user["id"]:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        session.expunge(job)
        return job


def _require_job_owner_or_admin(request: Request, job: Any) -> None:
    """Raise :class:`AuthorizationError` if the user can't mutate *job*."""
    user = _get_user(request)
    if user.get("is_admin"):
        return
    if job.run_as_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="manage",
        securable_type="job",
        full_name=str(job.name),
    )


@app.get("/api/jobs")
async def api_list_jobs(request: Request) -> list[dict[str, Any]]:
    """Return jobs visible to the current user.

    Admin sees everything; a regular user only sees jobs whose
    ``run_as_user_id`` matches their user id, matching the detail-page
    visibility so the two surfaces cannot drift.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = _latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    return [_serialize_job(r, last_run=latest.get(r.id)) for r in rows]


@app.post("/api/jobs")
async def api_create_job(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new job (admin-only).

    Two shapes are accepted:

    * Single-task (Sprint 19 compatibility):
      ``{name, cron_expr, kind, config, ...}`` — the scheduler walks
      ``job.kind`` / ``job.config`` directly.
    * DAG (Sprint 20):
      ``{name, cron_expr, tasks: [{name, kind, config, depends_on?,
      max_retries?, retry_backoff_seconds?}, ...], max_parallel_runs?}``.
      ``depends_on`` inside the payload references *task names* because
      the ids do not exist yet; the route resolves them to integer ids
      during insert and also validates the resulting graph is acyclic
      via :func:`pointlessql.services.scheduler.validate_dag` before
      committing so a bad payload never lands in the DB.

    ``run_as_user_id`` defaults to the caller so an admin scheduling a
    job for themselves does not have to look up their own id.
    """
    from croniter import croniter as _croniter

    from pointlessql.exceptions import ValidationError as _VE
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobTask as JobTaskModel

    _require_admin(request)
    user = _get_user(request)

    name = body.get("name")
    cron_expr = body.get("cron_expr")
    if not name or not cron_expr:
        raise _VE("name and cron_expr are required")
    if not _croniter.is_valid(str(cron_expr)):
        raise _VE(f"Invalid cron expression: {cron_expr!r}")

    tasks_payload = body.get("tasks")
    if tasks_payload is not None and not isinstance(tasks_payload, list):
        raise _VE("tasks must be a JSON array when provided")

    # Single-task shortcut: validate kind + config just like Sprint 19.
    if not tasks_payload:
        kind = body.get("kind")
        if not kind:
            raise _VE("kind is required when 'tasks' is not provided")
        _JOB_REGISTRY.get(str(kind))
        config = body.get("config") or {}
        if not isinstance(config, dict):
            raise _VE("config must be a JSON object")
    else:
        kind = body.get("kind") or "python"  # placeholder on the Job row
        config = {}
        # Pre-flight each task entry so we fail fast before any INSERT.
        task_names: set[str] = set()
        for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(entry, dict):
                raise _VE("each task must be a JSON object")
            t_entry: dict[str, Any] = entry
            t_name = t_entry.get("name")
            t_kind = t_entry.get("kind")
            if not t_name or not t_kind:
                raise _VE("each task requires name and kind")
            if t_name in task_names:
                raise _VE(f"duplicate task name: {t_name!r}")
            task_names.add(str(t_name))
            _JOB_REGISTRY.get(str(t_kind))
            t_config = t_entry.get("config") or {}
            if not isinstance(t_config, dict):
                raise _VE(f"task {t_name!r}: config must be a JSON object")
            t_deps = t_entry.get("depends_on") or []
            if not isinstance(t_deps, list):
                raise _VE(f"task {t_name!r}: depends_on must be a JSON array")

    run_as_user_id = int(body.get("run_as_user_id") or user["id"])
    is_paused = bool(body.get("is_paused", False))
    max_parallel_runs = int(body.get("max_parallel_runs") or 1)
    if max_parallel_runs < 1:
        raise _VE("max_parallel_runs must be >= 1")
    on_failure_url_raw = body.get("on_failure_url")
    on_failure_url: str | None = None
    if on_failure_url_raw is not None:
        if not isinstance(on_failure_url_raw, str) or not on_failure_url_raw.strip():
            raise _VE("on_failure_url must be a non-empty string when provided")
        on_failure_url = on_failure_url_raw.strip()

    now = datetime.now(UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        job = JobModel(
            name=str(name),
            cron_expr=str(cron_expr),
            run_as_user_id=run_as_user_id,
            kind=str(kind),
            config=json.dumps(config),
            is_paused=is_paused,
            max_parallel_runs=max_parallel_runs,
            on_failure_url=on_failure_url,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        # Flush-only, not commit: if DAG validation below fails, the
        # ``with factory() as session:`` context closes without commit
        # and the job row never lands in the DB (Sprint 23 BUG-23-02).
        session.flush()

        if tasks_payload:
            # First pass: insert rows without depends_on so we learn ids.
            by_name: dict[str, JobTaskModel] = {}
            for order, entry in enumerate(tasks_payload):  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry: dict[str, Any] = entry
                jt = JobTaskModel(
                    job_id=job.id,
                    name=str(t_entry["name"]),
                    order=order,
                    kind=str(t_entry["kind"]),
                    config=json.dumps(t_entry.get("config") or {}),
                    depends_on="[]",
                    max_retries=int(t_entry.get("max_retries") or 0),
                    retry_backoff_seconds=int(t_entry.get("retry_backoff_seconds") or 0),
                )
                session.add(jt)
                session.flush()
                by_name[str(t_entry["name"])] = jt

            # Second pass: resolve depends_on names to ids.
            for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry = entry
                t_name = str(t_entry["name"])
                deps_names = t_entry.get("depends_on") or []
                resolved: list[int] = []
                for dn in deps_names:  # pyright: ignore[reportUnknownVariableType]
                    if dn not in by_name:
                        raise _VE(f"task {t_name!r} depends on unknown task {dn!r}")
                    resolved.append(by_name[str(dn)].id)
                by_name[t_name].depends_on = json.dumps(resolved)

            # Validate the resulting graph is acyclic BEFORE committing
            # so a failed validation leaves no job or task rows behind.
            scheduler_service.validate_dag(list(by_name.values()))

        # All validation passed — commit job + tasks atomically.
        session.commit()
        session.refresh(job)
        session.expunge(job)
    await _audit(request, "create_job", f"job:{name}", json.dumps(body))
    return _serialize_job(job)


@app.post("/api/jobs/{job_id}/run")
async def api_run_job(request: Request, job_id: int) -> dict[str, Any]:
    """Manually trigger a run of *job_id* (admin or owner only)."""
    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(factory, settings, _JOB_REGISTRY, job_id, "manual")
    await _audit(request, "run_job", f"job:{job.name}")
    return _serialize_run(run)


@app.get("/api/jobs/{job_id}/tasks")
async def api_list_job_tasks(request: Request, job_id: int) -> list[dict[str, Any]]:
    """Return the :class:`JobTask` DAG nodes for *job_id*."""
    from sqlalchemy import select as _select

    from pointlessql.models import JobTask as JobTaskModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [_serialize_task(r) for r in rows]


@app.get("/api/jobs/{job_id}/runs/{run_id}/tasks")
async def api_list_task_runs(request: Request, job_id: int, run_id: int) -> list[dict[str, Any]]:
    """Return per-task state rows for one :class:`JobRun`."""
    from sqlalchemy import select as _select

    from pointlessql.models import TaskRun as TaskRunModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(TaskRunModel).where(TaskRunModel.job_run_id == run_id).order_by(TaskRunModel.id)
        )
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [_serialize_task_run(r) for r in rows]


@app.get("/api/jobs/{job_id}/runs/{run_id}/logs")
async def api_list_job_logs(
    request: Request,
    job_id: int,
    run_id: int,
    task_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return log lines for one :class:`JobRun`, optionally filtered by task.

    The log panel on the job detail page fetches this endpoint via
    Alpine.js when the user expands a row; ``task_id`` lets the panel
    scope the view to one DAG node.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobLog as JobLogModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobLogModel).where(JobLogModel.job_run_id == run_id)
        if task_id is not None:
            stmt = stmt.where(JobLogModel.task_id == task_id)
        stmt = stmt.order_by(JobLogModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [
        {
            "id": r.id,
            "job_run_id": r.job_run_id,
            "task_id": r.task_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "level": r.level,
            "message": r.message,
        }
        for r in rows
    ]


def _load_papermill_run_output_path(request: Request, job_id: int, run_id: int) -> Path:
    """Validate *run_id* belongs to papermill *job_id* and return its runs dir.

    Shared validator for the inline render route and the download route.
    Both need the same three checks: caller can see the job, the job is a
    papermill job, and *run_id* really belongs to *job_id*.

    Args:
        request: Incoming FastAPI request; visibility is enforced via
            :func:`_load_job_or_404`.
        job_id: The :class:`Job` id from the URL path.
        run_id: The :class:`JobRun` id from the URL path.

    Returns:
        The absolute ``runs/`` directory where ``{run_id}.ipynb`` lives.

    Raises:
        CatalogNotFoundError: If the job is not visible to the caller,
            the run does not belong to the job, or the job is not a
            papermill kind.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = _load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        run = session.get(JobRunModel, run_id)
        if run is None or run.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
    settings: Settings = request.app.state.settings
    return settings.jupyter.notebooks_dir.resolve() / "runs"


@app.get("/jobs/{job_id}/runs/{run_id}/notebook", response_class=HTMLResponse)
async def job_run_notebook(
    request: Request,
    job_id: int,
    run_id: int,
    exclude_input: bool = False,
) -> HTMLResponse:
    """Render an executed Papermill notebook inline.

    Returns the nbconvert ``lab``-template HTML body for
    ``{notebooks_dir}/runs/{run_id}.ipynb``. The job-detail page embeds
    this route in an iframe inside the "Output artifacts" card. A
    ``runs/{run_id}.html`` sidecar is written on first render so
    subsequent hits skip the nbconvert cost.

    When ``exclude_input=true`` is passed as a query param, the render
    hides code cells and caches to a sibling ``{run_id}.dashboard.html``
    sidecar — used by the Sprint 28 dashboard iframe to publish
    output-only views of the latest succeeded run.
    """
    runs_dir = _load_papermill_run_output_path(request, job_id, run_id)
    html = notebook_render_service.render_run_notebook(
        runs_dir, run_id, exclude_input=exclude_input
    )
    return HTMLResponse(html)


@app.get("/jobs/{job_id}/runs/{run_id}/notebook/download")
async def job_run_notebook_download(
    request: Request,
    job_id: int,
    run_id: int,
    format: Literal["ipynb", "html"] = "ipynb",
) -> FileResponse:
    """Download the raw ipynb or cached-HTML sidecar for a run.

    Sprint 26 chose a visibility-checked route over a StaticFiles mount
    so non-owner logged-in users cannot guess ``run_id`` values and
    exfiltrate another user's job output. ``format=html`` triggers a
    render if the sidecar is not yet present.
    """
    from pointlessql.exceptions import CatalogNotFoundError

    runs_dir = _load_papermill_run_output_path(request, job_id, run_id)
    if format == "html":
        # Ensure the sidecar exists before serving it.
        notebook_render_service.render_run_notebook(runs_dir, run_id)
        path = runs_dir / f"{run_id}.html"
        media_type = "text/html"
    else:
        path = runs_dir / f"{run_id}.ipynb"
        media_type = "application/x-ipynb+json"
    if not path.is_file():
        raise CatalogNotFoundError(f"Run {run_id} {format} artifact not found")
    return FileResponse(
        path,
        filename=f"job{job_id}_run{run_id}.{format}",
        media_type=media_type,
    )


@app.get("/jobs/{job_id}/runs/{run_id}/compare", response_class=HTMLResponse)
async def job_run_compare(
    request: Request,
    job_id: int,
    run_id: int,
    to: int,
) -> HTMLResponse:
    """Render two executed notebooks side-by-side for the same papermill job.

    Both runs must belong to ``job_id`` — this prevents leaking a peek
    at a different job's output by smuggling a foreign ``to=`` run id
    through the query string. The page itself embeds two Sprint 26
    ``/jobs/{id}/runs/{rid}/notebook`` iframes; no cell-level diffing
    (stub — that is a future sprint if demand emerges).
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = _load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        left = session.get(JobRunModel, run_id)
        right = session.get(JobRunModel, to)
        if left is None or left.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
        if right is None or right.job_id != job_id:
            raise CatalogNotFoundError(f"Run {to} not found for job {job_id}")
        session.expunge(left)
        session.expunge(right)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/run_compare.html",
        {
            "job": _serialize_job(job),
            "left": _serialize_run(left),
            "right": _serialize_run(right),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Dashboards (Sprint 28) --
# A dashboard is a stable slug-addressable view of a notebook job's
# latest succeeded run, rendered with ``exclude_input=True`` so
# consumers see outputs only. The ``job_id`` FK is nullable so a
# dashboard can outlive its bound job (FK uses ``ON DELETE SET NULL``);
# when no job is bound or no successful run exists, the detail page
# renders an empty state.


_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")


def _serialize_dashboard(dashboard: Any, *, latest_run_id: int | None = None) -> dict[str, Any]:
    """Render a :class:`Dashboard` ORM row for JSON + template responses."""
    return {
        "id": dashboard.id,
        "slug": dashboard.slug,
        "title": dashboard.title,
        "description": dashboard.description,
        "notebook_path": dashboard.notebook_path,
        "job_id": dashboard.job_id,
        "owner_id": dashboard.owner_id,
        "latest_run_id": latest_run_id,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    }


def _load_dashboard_or_404(request: Request, slug: str) -> Any:
    """Fetch a :class:`Dashboard` by slug; 404 when missing.

    Dashboards are visible to every logged-in user — they are the
    consumer-facing surface — so there is no per-user filter here.
    The admin gate lives on the mutating routes and on Refresh.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Dashboard as DashboardModel

    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            raise CatalogNotFoundError(f"Dashboard {slug!r} not found")
        session.expunge(row)
        return row


def _latest_succeeded_run_id(request: Request, job_id: int) -> int | None:
    """Return the most recent succeeded :class:`JobRun` id for *job_id*.

    Used by the dashboard detail route to pick which run's output to
    render. ``None`` when the job has never produced a successful run.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(JobRunModel.id)
            .where(JobRunModel.job_id == job_id)
            .where(JobRunModel.status == "succeeded")
            .order_by(JobRunModel.started_at.desc())
            .limit(1)
        )
        return session.scalar(stmt)


@app.get("/api/dashboards")
async def api_list_dashboards(request: Request) -> list[dict[str, Any]]:
    """Return every dashboard in creation order (any logged-in user)."""
    from sqlalchemy import select as _select

    from pointlessql.models import Dashboard as DashboardModel

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(DashboardModel).order_by(DashboardModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [_serialize_dashboard(r) for r in rows]


@app.get("/api/dashboards/tree")
async def api_dashboards_tree(request: Request) -> list[dict[str, Any]]:
    """Return a flat list shaped for the dashboards sidebar component.

    The shape mirrors the Sprint 27 workspace tree enough that the
    Alpine component is a straightforward copy. ``/api/dashboards``
    already returns the same rows — the dedicated tree endpoint keeps
    the Alpine fetch call symmetrical with the catalog tree.
    """
    return await api_list_dashboards(request)


def _score_match(needle: str, haystack: str) -> float | None:
    """Return the match score or ``None`` when *needle* is absent.

    Prefix matches outrank substring matches so that typing ``prod`` ranks
    ``prod_orders`` above ``backup_prod``. Needle is assumed already
    casefolded; haystack is casefolded here so callers can pass raw names.
    """
    if not haystack:
        return None
    hay = haystack.casefold()
    if hay.startswith(needle):
        return 2.0
    if needle in hay:
        return 1.0
    return None


def _epoch_seconds(value: Any) -> float:
    """Normalize a soyuz epoch-ms int or ORM ``datetime`` to float seconds.

    Used as the tiebreak key for `/api/search`. ``None`` and unrecognized
    types collapse to ``0.0`` so those hits always lose the tiebreak
    rather than raising mid-sort.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


@app.get("/api/search")
async def api_search(request: Request, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Aggregate global search hits for the Cmd+K command palette.

    Merges catalog / schema / table / federation objects from soyuz with
    local jobs, dashboards, and (for admins) workspace notebooks. Scoring
    favours prefix matches over substring matches; ties resolve by
    ``updated_at`` descending. An empty query returns ``[]``; the frontend
    renders the localStorage recent-searches in that case so we avoid the
    roundtrip entirely.

    Each soyuz source is wrapped individually: a partial outage (e.g. the
    connections list is momentarily 502) degrades to "those hits missing"
    rather than 502'ing the whole palette, which would make the shortcut
    disproportionately fragile for a supplementary navigation surface.
    """
    needle = q.strip().casefold()
    if not needle:
        return []
    limit = max(1, min(int(limit), 100))

    user = _get_user(request)
    client = _get_uc_client(request)

    async def _soyuz_tree() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            tree = await client.get_tree()
        except PointlessSQLError:
            logger.warning("search: soyuz tree unavailable", exc_info=True)
            return out
        for cat in tree:
            cat_name = str(cat.get("name") or "")
            cat_score = _score_match(needle, cat_name)
            if cat_score is not None:
                out.append(
                    {
                        "type": "catalog",
                        "label": cat_name,
                        "description": str(cat.get("comment") or ""),
                        "url": f"/catalogs/{cat_name}",
                        "updated_at": _epoch_seconds(cat.get("updated_at")),
                        "score": cat_score,
                    }
                )
            for schema in cat.get("schemas") or []:
                s_name = str(schema.get("name") or "")
                s_score = _score_match(needle, s_name)
                if s_score is not None:
                    out.append(
                        {
                            "type": "schema",
                            "label": f"{cat_name}.{s_name}",
                            "description": str(schema.get("comment") or ""),
                            "url": f"/catalogs/{cat_name}/schemas/{s_name}",
                            "updated_at": _epoch_seconds(schema.get("updated_at")),
                            "score": s_score,
                        }
                    )
                for table in schema.get("tables") or []:
                    t_name = str(table.get("name") or "")
                    t_score = _score_match(needle, t_name)
                    if t_score is None:
                        continue
                    out.append(
                        {
                            "type": "table",
                            "label": f"{cat_name}.{s_name}.{t_name}",
                            "description": str(table.get("comment") or ""),
                            "url": (f"/catalogs/{cat_name}/schemas/{s_name}/tables/{t_name}"),
                            "updated_at": _epoch_seconds(table.get("updated_at")),
                            "score": t_score,
                        }
                    )
        return out

    async def _soyuz_federation() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        sources: list[tuple[str, Any, str]] = [
            ("connection", client.list_connections, "/connections/{name}"),
            ("credential", client.list_credentials, "/credentials/{name}"),
            (
                "external_location",
                client.list_external_locations,
                "/external-locations/{name}",
            ),
        ]
        for type_name, fetcher, url_tmpl in sources:
            try:
                rows = await fetcher()
            except PointlessSQLError:
                logger.warning("search: %s list unavailable", type_name, exc_info=True)
                continue
            for row in rows:
                name = str(row.get("name") or "")
                score = _score_match(needle, name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": type_name,
                        "label": name,
                        "description": str(row.get("comment") or ""),
                        "url": url_tmpl.format(name=name),
                        "updated_at": _epoch_seconds(row.get("updated_at")),
                        "score": score,
                    }
                )
        return out

    def _local_jobs() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Job as JobModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            stmt = _select(JobModel)
            if not user.get("is_admin"):
                stmt = stmt.where(JobModel.run_as_user_id == user["id"])
            for row in session.scalars(stmt).all():
                score = _score_match(needle, row.name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": "job",
                        "label": row.name,
                        "description": f"{row.kind} · {row.cron_expr}",
                        "url": f"/jobs/{row.id}",
                        "updated_at": _epoch_seconds(row.updated_at),
                        "score": score,
                    }
                )
        return out

    def _local_dashboards() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            for row in session.scalars(_select(DashboardModel)).all():
                title_score = _score_match(needle, row.title)
                slug_score = _score_match(needle, row.slug)
                score = title_score
                if slug_score is not None and (score is None or slug_score > score):
                    score = slug_score
                if score is None:
                    continue
                out.append(
                    {
                        "type": "dashboard",
                        "label": row.title,
                        "description": row.description or row.slug,
                        "url": f"/dashboards/{row.slug}",
                        "updated_at": _epoch_seconds(row.updated_at),
                        "score": score,
                    }
                )
        return out

    def _local_notebooks() -> list[dict[str, Any]]:
        # Matches the Sprint-27 admin boundary on /api/notebooks/tree.
        if not user.get("is_admin"):
            return []
        settings_obj: Settings = request.app.state.settings
        try:
            tree = notebook_workspace_service.list_workspace_tree(
                settings_obj.jupyter.notebooks_dir.resolve()
            )
        except Exception:
            logger.warning("search: notebook tree unavailable", exc_info=True)
            return []
        out: list[dict[str, Any]] = []

        def _walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                kind = node.get("kind")
                if kind == "notebook":
                    name = str(node.get("name") or "")
                    path = str(node.get("path") or "")
                    score = _score_match(needle, name) or _score_match(needle, path)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "notebook",
                            "label": name,
                            "description": path,
                            "url": f"/notebooks/workspace?path={path}",
                            "updated_at": 0.0,
                            "score": score,
                        }
                    )
                elif kind == "dir":
                    children = node.get("children") or []
                    _walk(children)

        _walk(tree)
        return out

    tree_hits, fed_hits = await asyncio.gather(_soyuz_tree(), _soyuz_federation())
    hits: list[dict[str, Any]] = []
    hits.extend(tree_hits)
    hits.extend(fed_hits)
    hits.extend(_local_jobs())
    hits.extend(_local_dashboards())
    hits.extend(_local_notebooks())

    hits.sort(key=lambda h: (-float(h["score"]), -float(h["updated_at"])))
    return hits[:limit]


async def _build_home_summary(request: Request, user: UserInfo) -> dict[str, Any]:
    """Aggregate the payload that powers the home dashboard.

    Shared by the HTML ``/`` handler and the JSON ``/api/home/summary``
    endpoint so first-paint and subsequent refreshes see the same
    shape. The soyuz catalog count is fetched concurrently with the
    local DB aggregates; a soyuz outage downgrades to
    ``catalogs.unavailable = True`` but does not fail the whole
    response, matching the error-resilience rule used by
    ``/api/search`` above.

    Args:
        request: The incoming FastAPI request. Used for the UC client
            and the session factory.
        user: The current user's info dict.

    Returns:
        A dict with keys ``user``, ``catalogs``, ``jobs``,
        ``dashboards``, ``latest_runs``, ``sparkline``, and
        ``onboarding``. See ``/api/home/summary`` for the documented
        shape.
    """
    client = _get_uc_client(request)
    is_admin = bool(user.get("is_admin"))
    user_id = int(user.get("id") or 0)

    async def _catalogs_block() -> dict[str, Any]:
        try:
            catalogs = await client.list_catalogs()
        except CatalogUnavailableError as exc:
            logger.warning("home: soyuz catalog list unavailable", exc_info=True)
            return {
                "count": 0,
                "has_catalogs": False,
                "unavailable": True,
                "error": exc.detail,
            }
        count = len(catalogs)
        return {
            "count": count,
            "has_catalogs": count > 0,
            "unavailable": False,
            "error": None,
        }

    def _db_block() -> dict[str, Any]:
        from sqlalchemy import func
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel
        from pointlessql.models import Job as JobModel
        from pointlessql.models import JobRun as JobRunModel

        factory = request.app.state.session_factory
        with factory() as session:
            jobs_stmt = _select(JobModel)
            if not is_admin:
                jobs_stmt = jobs_stmt.where(JobModel.run_as_user_id == user_id)
            jobs_rows = list(session.scalars(jobs_stmt).all())
            count_visible = len(jobs_rows)
            count_paused = sum(1 for j in jobs_rows if j.is_paused)
            visible_job_ids = [j.id for j in jobs_rows]

            latest_runs: list[dict[str, Any]] = []
            if visible_job_ids:
                runs_stmt = (
                    _select(JobRunModel, JobModel.name)
                    .join(JobModel, JobRunModel.job_id == JobModel.id)
                    .where(JobRunModel.job_id.in_(visible_job_ids))
                    .order_by(JobRunModel.started_at.desc())
                    .limit(10)
                )
                for run, job_name in session.execute(runs_stmt).all():
                    duration: float | None = None
                    if run.started_at and run.finished_at:
                        duration = (run.finished_at - run.started_at).total_seconds()
                    latest_runs.append(
                        {
                            "id": run.id,
                            "job_id": run.job_id,
                            "job_name": job_name,
                            "status": run.status,
                            "trigger": run.trigger,
                            "started_at": run.started_at.isoformat() if run.started_at else None,
                            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                            "duration_s": duration,
                        }
                    )

            # 7-day rolling window including today. Only terminal runs
            # (succeeded + failed) count: pending/running would make the
            # rate drift mid-day, skipped is a scheduler signal, not a
            # real outcome.
            today = datetime.now(UTC).date()
            start_day = today - timedelta(days=6)
            window_start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
            days: list[dict[str, Any]] = [
                {
                    "date": (start_day + timedelta(days=i)).isoformat(),
                    "total": 0,
                    "succeeded": 0,
                    "rate": None,
                }
                for i in range(7)
            ]
            if visible_job_ids:
                spark_stmt = (
                    _select(JobRunModel.started_at, JobRunModel.status)
                    .where(JobRunModel.job_id.in_(visible_job_ids))
                    .where(JobRunModel.started_at >= window_start)
                    .where(JobRunModel.status.in_(["succeeded", "failed"]))
                )
                for started_at, status in session.execute(spark_stmt).all():
                    idx = (started_at.date() - start_day).days
                    if 0 <= idx < 7:
                        bucket = days[idx]
                        bucket["total"] += 1
                        if status == "succeeded":
                            bucket["succeeded"] += 1
                for bucket in days:
                    if bucket["total"] > 0:
                        bucket["rate"] = bucket["succeeded"] / bucket["total"]
            # Pre-compute the SVG bar styling server-side. Alpine's
            # ``<template x-for>`` inside ``<svg>`` doesn't work —
            # ``<template>.content`` is HTML-namespaced so inner
            # ``<rect>`` elements get parsed as unknown HTML, leaving
            # the bars unbound (BUG-32-01 found during the Phase 9
            # playbook replay). Moving the branch here keeps the
            # template a plain Jinja ``{% for %}`` loop.
            for bucket in days:
                rate = bucket["rate"]
                if rate is None:
                    bucket["bar_height"] = 2
                    bucket["bar_class"] = "pql-spark--empty"
                    bucket["bar_title"] = f"{bucket['date']}: no runs"
                else:
                    bucket["bar_height"] = round(max(2.0, rate * 36), 2)
                    if rate >= 0.9:
                        bucket["bar_class"] = "pql-spark--ok"
                    elif rate >= 0.5:
                        bucket["bar_class"] = "pql-spark--warn"
                    else:
                        bucket["bar_class"] = "pql-spark--bad"
                    pct = round(rate * 100)
                    bucket["bar_title"] = (
                        f"{bucket['date']}: {bucket['succeeded']}/"
                        f"{bucket['total']} succeeded ({pct}%)"
                    )

            count_total = session.scalar(_select(func.count()).select_from(DashboardModel)) or 0
            count_mine = (
                session.scalar(
                    _select(func.count())
                    .select_from(DashboardModel)
                    .where(DashboardModel.owner_id == user_id)
                )
                or 0
            )
            mine_rows = list(
                session.scalars(
                    _select(DashboardModel)
                    .where(DashboardModel.owner_id == user_id)
                    .order_by(DashboardModel.updated_at.desc())
                    .limit(5)
                ).all()
            )
            mine: list[dict[str, Any]] = [
                {
                    "slug": d.slug,
                    "title": d.title,
                    "notebook_path": d.notebook_path,
                    "job_id": d.job_id,
                    "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                }
                for d in mine_rows
            ]

        return {
            "jobs": {"count_visible": count_visible, "count_paused": count_paused},
            "dashboards": {
                "count_total": int(count_total),
                "count_mine": int(count_mine),
                "mine": mine,
            },
            "latest_runs": latest_runs,
            "sparkline": {"days": days},
        }

    catalogs_block, db_block = await asyncio.gather(
        _catalogs_block(),
        asyncio.to_thread(_db_block),
    )

    have_catalogs = bool(catalogs_block["has_catalogs"])
    have_jobs = db_block["jobs"]["count_visible"] > 0
    have_dashboards = db_block["dashboards"]["count_total"] > 0
    unavailable = bool(catalogs_block["unavailable"])
    # Suppress onboarding when soyuz is down — "connect a data source"
    # is the wrong prompt for a user whose data is fine but whose
    # catalog server is momentarily unreachable.
    show_onboarding = (
        not unavailable and not have_catalogs and not have_jobs and not have_dashboards
    )

    return {
        "user": {
            "display_name": user.get("display_name") or user.get("email", ""),
            "email": user.get("email", ""),
            "is_admin": is_admin,
        },
        "catalogs": catalogs_block,
        "jobs": db_block["jobs"],
        "dashboards": db_block["dashboards"],
        "latest_runs": db_block["latest_runs"],
        "sparkline": db_block["sparkline"],
        "onboarding": {
            "show": show_onboarding,
            "have_catalogs": have_catalogs,
            "have_jobs": have_jobs,
            "have_dashboards": have_dashboards,
        },
    }


@app.get("/api/home/summary")
async def api_home_summary(request: Request) -> dict[str, Any]:
    """Return the aggregated payload that powers the home dashboard.

    One round-trip for every server-side card on ``/``: catalog count,
    jobs + paused counters, 10 most recent cross-job runs visible to
    the user, a 7-day success-rate bucket list for the sparkline, and
    the user's own dashboards + total dashboard count. Recent catalogs
    are client-side in ``localStorage["pql.recentCatalogs"]`` and do
    not flow through this endpoint.
    """
    user = _get_user(request)
    return await _build_home_summary(request, user)


@app.post("/api/dashboards")
async def api_create_dashboard(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a new dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
    user = _get_user(request)

    slug_raw = body.get("slug")
    title = body.get("title")
    notebook_path = body.get("notebook_path")
    if not slug_raw or not title or not notebook_path:
        raise ValidationError("slug, title and notebook_path are required")
    slug = str(slug_raw).strip()
    if not _SLUG_PATTERN.match(slug):
        raise ValidationError("slug must be lowercase letters, digits and hyphens (1-200 chars)")

    description_raw = body.get("description")
    description: str | None = None
    if description_raw is not None:
        if not isinstance(description_raw, str):
            raise ValidationError("description must be a string when provided")
        description = description_raw.strip() or None

    job_id_raw = body.get("job_id")
    job_id: int | None = None
    if job_id_raw not in (None, ""):
        try:
            job_id = int(job_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError("job_id must be an integer") from exc

    now = datetime.now(UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        existing = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if existing is not None:
            raise ValidationError(f"dashboard slug {slug!r} already exists")

        dashboard = DashboardModel(
            slug=slug,
            title=str(title).strip(),
            description=description,
            notebook_path=str(notebook_path).strip(),
            job_id=job_id,
            owner_id=user["id"],
            created_at=now,
            updated_at=now,
        )
        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)
        session.expunge(dashboard)
    await _audit(request, "create_dashboard", f"dashboard:{slug}", json.dumps(body))
    return _serialize_dashboard(dashboard)


@app.patch("/api/dashboards/{slug}")
async def api_update_dashboard(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Update mutable dashboard fields (admin-only).

    Editable: title, description, notebook_path, job_id. slug and
    owner_id are immutable — delete + recreate if the URL or owner
    needs to change so callers never observe a half-migrated row.
    """
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            from pointlessql.exceptions import CatalogNotFoundError as _NF

            raise _NF(f"Dashboard {slug!r} not found")

        if "title" in body:
            title = body["title"]
            if not isinstance(title, str) or not title.strip():
                raise ValidationError("title must be a non-empty string")
            row.title = title.strip()
        if "description" in body:
            desc = body["description"]
            if desc is not None and not isinstance(desc, str):
                raise ValidationError("description must be a string or null")
            row.description = desc.strip() if isinstance(desc, str) and desc.strip() else None
        if "notebook_path" in body:
            path = body["notebook_path"]
            if not isinstance(path, str) or not path.strip():
                raise ValidationError("notebook_path must be a non-empty string")
            row.notebook_path = path.strip()
        if "job_id" in body:
            jid = body["job_id"]
            if jid in (None, ""):
                row.job_id = None
            else:
                try:
                    row.job_id = int(jid)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("job_id must be an integer or null") from exc
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await _audit(request, "update_dashboard", f"dashboard:{slug}", json.dumps(body))
    return _serialize_dashboard(row)


@app.delete("/api/dashboards/{slug}")
async def api_delete_dashboard(request: Request, slug: str) -> dict[str, str]:
    """Delete a dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            from pointlessql.exceptions import CatalogNotFoundError as _NF

            raise _NF(f"Dashboard {slug!r} not found")
        session.delete(row)
        session.commit()
    await _audit(request, "delete_dashboard", f"dashboard:{slug}")
    return {"status": "deleted", "slug": slug}


@app.post("/api/dashboards/{slug}/refresh")
async def api_refresh_dashboard(request: Request, slug: str) -> dict[str, Any]:
    """Trigger a manual run of the bound job (admin-only).

    Thin wrapper over the scheduler's manual-run helper that powers
    the job-detail "Run now" button — no new execution concept, just
    a shortcut for the dashboard consumer UI.
    """
    _require_admin(request)
    dashboard = _load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise ValidationError("dashboard has no bound job to refresh")
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(
        factory, settings, _JOB_REGISTRY, dashboard.job_id, "manual"
    )
    await _audit(request, "refresh_dashboard", f"dashboard:{slug}")
    return _serialize_run(run)


@app.get("/dashboards", response_class=HTMLResponse)
async def dashboards_index(request: Request) -> HTMLResponse:
    """Render the dashboards list page (any logged-in user)."""
    from sqlalchemy import select as _select

    from pointlessql.models import Dashboard as DashboardModel
    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(DashboardModel).order_by(DashboardModel.id)
        dashboards = list(session.scalars(stmt).all())
        for d in dashboards:
            session.expunge(d)
        # Admins can bind dashboards to any job; fetch the job list
        # once so the create modal's <select> doesn't need an extra
        # round-trip on open.
        job_options: list[dict[str, Any]] = []
        if user.get("is_admin"):
            for j in session.scalars(_select(JobModel).order_by(JobModel.name)).all():
                job_options.append({"id": j.id, "name": j.name, "kind": j.kind})
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/dashboards.html",
        {
            "dashboards": [_serialize_dashboard(d) for d in dashboards],
            "is_admin": user.get("is_admin", False),
            "job_options": job_options,
            "active_page": "dashboards",
            "active_dashboard_slug": None,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@app.get("/dashboards/{slug}", response_class=HTMLResponse)
async def dashboard_detail(request: Request, slug: str) -> HTMLResponse:
    """Render a dashboard's latest-run output (any logged-in user).

    The iframe src points at :func:`dashboard_output` so the visibility
    boundary is the dashboard itself, not the underlying job — dashboards
    are a consumer/publishing surface. When the bound job has never
    produced a succeeded run — or there is no bound job at all — the
    page renders an empty state instead.
    """
    user = _get_user(request)
    dashboard = _load_dashboard_or_404(request, slug)
    latest_run_id: int | None = None
    if dashboard.job_id is not None:
        latest_run_id = _latest_succeeded_run_id(request, dashboard.job_id)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/dashboard_detail.html",
        {
            "dashboard": _serialize_dashboard(dashboard, latest_run_id=latest_run_id),
            "is_admin": user.get("is_admin", False),
            "active_page": "dashboards",
            "active_dashboard_slug": slug,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/dashboards/{slug}/output", response_class=HTMLResponse)
async def dashboard_output(request: Request, slug: str) -> HTMLResponse:
    """Render the code-hidden HTML of the dashboard's latest succeeded run.

    This is the iframe source for the dashboard detail page. Unlike
    :func:`job_run_notebook` it does **not** go through
    :func:`_load_papermill_run_output_path` — which enforces
    admin-or-job-owner visibility — because dashboards are a
    consumer-facing publishing surface: any logged-in user who can see
    the dashboard metadata must be able to see the output it publishes.
    The visibility guard here is the dashboard's existence + a single
    internal check that the run belongs to the bound job.

    Args:
        request: Incoming FastAPI request; any logged-in user.
        slug: Dashboard slug from the URL path.

    Returns:
        HTMLResponse with the nbconvert code-hidden render.

    Raises:
        CatalogNotFoundError: When the dashboard doesn't exist, when it
            has no bound job, or when the bound job has no succeeded run.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel

    dashboard = _load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise CatalogNotFoundError(f"Dashboard {slug!r} has no bound job")
    latest_run_id = _latest_succeeded_run_id(request, dashboard.job_id)
    if latest_run_id is None:
        raise CatalogNotFoundError(f"Dashboard {slug!r} has no succeeded run yet")

    factory = request.app.state.session_factory
    with factory() as session:
        job = session.get(JobModel, dashboard.job_id)
        run = session.get(JobRunModel, latest_run_id)
        if job is None or run is None or run.job_id != dashboard.job_id:
            raise CatalogNotFoundError(f"Dashboard {slug!r} output not available")
        if job.kind != "papermill":
            raise CatalogNotFoundError(f"Dashboard {slug!r} bound job is not a papermill job")

    settings: Settings = request.app.state.settings
    runs_dir = settings.jupyter.notebooks_dir.resolve() / "runs"
    html = notebook_render_service.render_run_notebook(runs_dir, latest_run_id, exclude_input=True)
    return HTMLResponse(html)


@app.post("/api/jobs/{job_id}/pause")
async def api_pause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Pause *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = True
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await _audit(request, "pause_job", f"job:{row.name}")
    return _serialize_job(row)


@app.post("/api/jobs/{job_id}/unpause")
async def api_unpause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Resume *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = False
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await _audit(request, "unpause_job", f"job:{row.name}")
    return _serialize_job(row)


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_index(request: Request) -> HTMLResponse:
    """List every job visible to the current user."""
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = _latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    jobs_data = [_serialize_job(r, last_run=latest.get(r.id)) for r in rows]
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/jobs.html",
        {
            "jobs": jobs_data,
            "is_admin": user.get("is_admin", False),
            "current_user_id": user.get("id"),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


_ADMIN_AUDIT_LIMIT = 1000
_ADMIN_AUDIT_SINCE_WINDOWS: dict[str, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


@app.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_index(
    request: Request,
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> HTMLResponse:
    """Render the admin audit-log viewer.

    Reads from the Sprint-7 ``audit_log`` table (written append-only
    by every admin state-change via :func:`_audit`) and shows the
    newest :data:`_ADMIN_AUDIT_LIMIT` rows matching the requested
    filters. Admin-gated because the log carries cross-user activity
    that a non-admin principal must not see. Re-uses the ``/jobs``
    ``listTable`` Alpine component for search and chip filtering so
    the page inherits sorting, search, and mobile stacking without
    new frontend primitives.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    _require_admin(request)
    current_user = _get_user(request)
    factory = request.app.state.session_factory

    since_delta = _ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    # Fetch one extra row so we can tell the page whether the
    # ``_ADMIN_AUDIT_LIMIT`` cap hid older history.
    stmt = stmt.limit(_ADMIN_AUDIT_LIMIT + 1)

    with factory() as session:
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)

    truncated = len(rows) > _ADMIN_AUDIT_LIMIT
    if truncated:
        rows = rows[:_ADMIN_AUDIT_LIMIT]

    entries = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "target": r.target,
            "client_ip": r.client_ip,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
    # Distinct action list for the server-side filter dropdown.
    # Derived from the currently-loaded page so new actions show up
    # automatically; the 1000-row cap keeps this cheap.
    distinct_actions = sorted({e["action"] for e in entries})

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/admin_audit.html",
        {
            "entries": entries,
            "distinct_actions": distinct_actions,
            "filter_action": action or "",
            "filter_user": user or "",
            "filter_target": target or "",
            "filter_since": since,
            "truncated": truncated,
            "row_limit": _ADMIN_AUDIT_LIMIT,
            "current_user_id": current_user.get("id"),
            "current_user_email": current_user.get("email"),
            "active_page": "admin_audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


_AUDIT_EXPORT_LIMIT = 10_000
_AUDIT_EXPORT_FORMATS: tuple[str, ...] = ("json", "csv")


@app.get("/admin/audit/export")
async def admin_audit_export(
    request: Request,
    fmt: Literal["json", "csv"] = "json",
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> Response:
    """Stream the filtered audit log as JSON or CSV.

    Mirrors the :func:`admin_audit_index` filter surface so
    operators can "what you see is what you export" from the same
    query string — just swap ``/admin/audit?…`` for
    ``/admin/audit/export?fmt=csv&…``.  Capped at
    :data:`_AUDIT_EXPORT_LIMIT` rows per call so a broad ``since=all``
    query cannot blow memory; operators wanting more paginate by
    shrinking the time window.

    Args:
        request: The incoming HTTP request (used for admin gate).
        fmt: ``json`` or ``csv``.
        action: Optional exact-match action filter.
        user: Optional ``ILIKE %…%`` filter on ``user_email``.
        target: Optional ``ILIKE %…%`` filter on ``target``.
        since: Time-window preset (same as the HTML viewer).

    Returns:
        Response: Content-Disposition-attachment response; the
            download filename embeds the export timestamp.
    """
    import csv
    import io

    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    _require_admin(request)
    factory = request.app.state.session_factory

    since_delta = _ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    stmt = stmt.limit(_AUDIT_EXPORT_LIMIT)

    def _rows() -> list[dict[str, Any]]:
        with factory() as session:
            result = list(session.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "user_id": r.user_id,
                "user_email": r.user_email,
                "actor_role": r.actor_role,
                "action": r.action,
                "target": r.target,
                "client_ip": r.client_ip or "",
                "detail": r.detail or "",
            }
            for r in result
        ]

    rows = await asyncio.to_thread(_rows)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if fmt == "json":
        body = json.dumps({"exported_at": timestamp, "entries": rows}, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="pql-audit-{timestamp}.json"'
                )
            },
        )

    # CSV
    buf = io.StringIO()
    columns = [
        "id",
        "created_at",
        "user_id",
        "user_email",
        "actor_role",
        "action",
        "target",
        "client_ip",
        "detail",
    ]
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="pql-audit-{timestamp}.csv"'
            )
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int) -> HTMLResponse:
    """Render job detail with task list, latest task statuses, and run history."""
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel
    from pointlessql.models import JobTask as JobTaskModel
    from pointlessql.models import TaskRun as TaskRunModel

    job = _load_job_or_404(request, job_id)
    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        runs_stmt = (
            _select(JobRunModel)
            .where(JobRunModel.job_id == job_id)
            .order_by(JobRunModel.started_at.desc())
            .limit(20)
        )
        runs = list(session.scalars(runs_stmt).all())
        for r in runs:
            session.expunge(r)

        tasks_stmt = (
            _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        )
        tasks = list(session.scalars(tasks_stmt).all())
        for t in tasks:
            session.expunge(t)

        # Fetch the latest :class:`TaskRun` per task so the table can
        # show current status + retry count without a second round-trip.
        latest_task_runs: dict[int, Any] = {}
        if runs and tasks:
            latest_run_id = runs[0].id
            tr_stmt = _select(TaskRunModel).where(TaskRunModel.job_run_id == latest_run_id)
            for tr in session.scalars(tr_stmt).all():
                session.expunge(tr)
                latest_task_runs[tr.task_id] = tr

    can_manage = user.get("is_admin", False) or job.run_as_user_id == user.get("id")

    task_rows: list[dict[str, Any]] = []
    for t in tasks:
        tr = latest_task_runs.get(t.id)
        task_rows.append(
            {
                **_serialize_task(t),
                "latest_status": tr.status if tr is not None else None,
                "latest_attempts": tr.attempts if tr is not None else 0,
                "latest_error": tr.error if tr is not None else None,
                "latest_run_id": tr.job_run_id if tr is not None else None,
            }
        )

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/job_detail.html",
        {
            "job": _serialize_job(job),
            "runs": [_serialize_run(r) for r in runs],
            "tasks": task_rows,
            "can_manage": can_manage,
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


def cli() -> None:
    """Run the development server."""
    import uvicorn

    settings = Settings()
    # Why: uvicorn's reload watcher defaults to the whole working directory.
    # That includes ``notebooks/``, so the editor's autosave triggers a server
    # reload — kernel + Pyright WebSockets get torn down mid-typing
    # (Sprint 64 BUG-64-03). Pinning reload_dirs to the source trees keeps
    # autosave invisible to the watcher; SQLite files (.db) and Delta tables
    # (notebooks/, /tmp) stay outside scope.
    project_root = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "pointlessql.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        reload_dirs=[str(project_root), str(project_root.parent / "frontend")],
    )
