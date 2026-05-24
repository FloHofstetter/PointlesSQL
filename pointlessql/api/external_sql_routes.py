"""``/api/2.0/sql/statements`` — public DBX-compatible SQL API.

Phase 117 opens the first **token-only** REST surface for external
SQL clients (curl, dbt, BI tools) to run SELECT queries against the
PointlesSQL lakehouse without driving the browser UI.

Wire shape mirrors the documented Databricks SQL Statement Execution
API so the official ``databricks-sql-python`` client, the
``dbt-databricks`` adapter, and JDBC drivers can swap base-URLs and
work with minimal adapter glue.

Four endpoints:

* ``POST   /api/2.0/sql/statements``                              — submit
* ``GET    /api/2.0/sql/statements/{id}``                         — poll
* ``GET    /api/2.0/sql/statements/{id}/result/chunks/{idx}``     — fetch chunk
* ``POST   /api/2.0/sql/statements/{id}/cancel``                  — cancel
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlglot.errors import ParseError

from pointlessql.api._dbx_error_wrapper import (
    _dbx_error_response as _dbx_error_response,
)
from pointlessql.api._dbx_error_wrapper import (
    _DbxApiError as _DbxApiError,
)
from pointlessql.api._dbx_error_wrapper import (
    _wrap_dbx as _wrap_dbx,
)
from pointlessql.api.dependencies import effective_principal, require_sql_execute
from pointlessql.models import SqlStatement
from pointlessql.services import rate_limit as rate_limit_service
from pointlessql.services.sql_statements import (
    bind_parameters,
    cancel_statement,
    error_envelope,
    fetch_statement,
    qualify_sql,
    register_statement_task,
    run_statement,
)
from pointlessql.services.sql_statements._envelope import status_envelope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql-statements"])


# Accept "10s" / "10000ms" / bare "10".  DBX docs use the "<n>s" form
# but tolerating bare numbers makes ad-hoc curl friendlier.
_TIMEOUT_RE = re.compile(r"^\s*(\d+)\s*(s|ms)?\s*$", re.IGNORECASE)


def _parse_wait_timeout(raw: Any, default_s: int, max_s: int) -> int:
    """Parse the DBX-shape ``wait_timeout`` body field to seconds.

    Args:
        raw: Body value (string or number, or ``None``).
        default_s: Fallback when *raw* is missing / blank.
        max_s: Upper bound; values above clamp down.

    Returns:
        Seconds in ``[0, max_s]``.  ``0`` means "always async".

    Raises:
        _DbxApiError: With status 400 when the format is unparseable.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default_s
    if isinstance(raw, (int, float)):
        seconds = int(raw)
    elif isinstance(raw, str):
        match = _TIMEOUT_RE.match(raw)
        if not match:
            raise _DbxApiError(
                400,
                {
                    "error_code": "INVALID_PARAMETER_VALUE",
                    "message": (
                        f"wait_timeout {raw!r} is not a valid duration; "
                        f"expected '<n>s' (e.g. '10s')"
                    ),
                },
            )
        value = int(match.group(1))
        unit = (match.group(2) or "s").lower()
        seconds = value if unit == "s" else value // 1000
    else:
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "wait_timeout must be a string like '10s' or an int",
            },
        )
    if seconds < 0:
        seconds = 0
    if seconds > max_s:
        seconds = max_s
    return seconds


def _require_enabled(request: Request) -> None:
    """Reject every call with 503 when the API is disabled by settings."""
    settings = request.app.state.settings
    if not settings.sql_execution_api.enabled:
        raise _DbxApiError(
            503,
            {
                "error_code": "WORKSPACE_TEMPORARILY_UNAVAILABLE",
                "message": "The SQL Statement Execution API is disabled on this deployment.",
            },
        )


def _enforce_rate_limit(request: Request) -> None:
    """Bucket per-API-key-id; reject with DBX-shape 429 when exceeded.

    Lives inline rather than in the global rate-limit middleware
    because the response shape is DBX-specific (JSON envelope, not
    HTML).  Settings are read off the same ``rate_limit`` group so
    operators tune it in one place.

    Args:
        request: Incoming FastAPI request.

    Raises:
        _DbxApiError: With status 429 when the per-key bucket is full.
    """
    settings = request.app.state.settings
    rate_cfg = getattr(settings, "rate_limit", None)
    if rate_cfg is None or not getattr(rate_cfg, "enabled", True):
        return
    count = int(getattr(rate_cfg, "sql_statements_apikey_count", 0))
    window = int(getattr(rate_cfg, "sql_statements_apikey_window_s", 0))
    if count <= 0 or window <= 0:
        return
    api_key_id = getattr(request.state, "api_key_id", 0)
    if not api_key_id:
        # No keyed identity → skip the bucket; ``require_sql_execute``
        # already rejected cookie-only callers, so this only fires in
        # unit tests that hand-set api_key flags on request.state.
        return
    factory = request.app.state.session_factory
    bucket = rate_limit_service.bucket_for("sql_statements", "apikey", str(api_key_id))
    allowed, retry_after = rate_limit_service.check_and_record(factory, bucket, count, window)
    if not allowed:
        raise _DbxApiError(
            429,
            {
                "error_code": "REQUEST_LIMIT_EXCEEDED",
                "message": (
                    f"Per-API-key submission rate exceeded "
                    f"({count} per {window}s); retry after {retry_after}s."
                ),
            },
            headers={"Retry-After": str(retry_after)},
        )


def _persist_pending(
    request: Request,
    *,
    statement_id: str,
    api_key_id: int,
    user_id: int,
    workspace_id: int,
    statement_text: str,
    catalog: str | None,
    schema_name: str | None,
    row_limit: int,
) -> None:
    """Insert the initial PENDING row before launching the executor."""
    factory = request.app.state.session_factory
    with factory() as session:
        session.add(
            SqlStatement(
                statement_id=statement_id,
                api_key_id=api_key_id,
                submitted_by_user_id=user_id,
                workspace_id=workspace_id,
                statement_text=statement_text[:65536],
                catalog=catalog,
                schema_name=schema_name,
                row_limit=row_limit,
                status="PENDING",
                submitted_at=datetime.now(UTC),
                cancel_requested=False,
            )
        )
        session.commit()


def _normalise_body(body: dict[str, Any] | None) -> dict[str, Any]:
    """Return a defensive copy + replace ``None`` with sane defaults."""
    if not isinstance(body, dict):
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "Request body must be a JSON object.",
            },
        )
    return dict(body)


@router.post("/api/2.0/sql/statements")
@_wrap_dbx
async def submit_statement(
    request: Request,
    body: dict[str, Any] = Body(...),
    _: None = Depends(require_sql_execute),
) -> JSONResponse:
    """Submit a SQL statement for execution.

    Honours the DBX-compatible request body:

    * ``statement`` (required) — the SQL text.
    * ``catalog`` / ``schema`` — defaults for 2-/1-part table refs.
    * ``wait_timeout`` (default ``"10s"``) — how long to wait inline
      before returning a PENDING envelope the client polls.
    * ``on_wait_timeout`` (``CONTINUE`` | ``CANCEL``) — what to do
      when the wait_timeout elapses.
    * ``format`` (``JSON_ARRAY``) — only JSON_ARRAY supported in v1.
    * ``disposition`` (``INLINE``) — only INLINE supported in v1.
    * ``row_limit`` — capped at ``max_row_limit``.
    * ``parameters`` — typed ``:name`` binding entries.

    The route returns immediately for fast queries (SUCCEEDED envelope
    inline); slower queries return a PENDING envelope the client polls.

    Args:
        request: Incoming FastAPI request.
        body: Parsed JSON body.

    Returns:
        DBX-shape :class:`JSONResponse`.

    Raises:
        _DbxApiError: For body validation errors (400), unsupported
            options (400), rate-limit (429), or disabled-API (503).
    """
    _require_enabled(request)
    _enforce_rate_limit(request)
    payload = _normalise_body(body)

    statement_text = payload.get("statement")
    if not isinstance(statement_text, str) or not statement_text.strip():
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "'statement' is required and must be a non-empty string.",
            },
        )

    fmt = (payload.get("format") or "JSON_ARRAY").upper()
    if fmt != "JSON_ARRAY":
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": f"format={fmt!r} is not supported in v1; only 'JSON_ARRAY'.",
            },
        )
    disposition = (payload.get("disposition") or "INLINE").upper()
    if disposition != "INLINE":
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": (f"disposition={disposition!r} is not supported in v1; only 'INLINE'."),
            },
        )

    settings = request.app.state.settings
    sql_cfg = settings.sql_execution_api

    catalog = payload.get("catalog")
    catalog = catalog.strip() if isinstance(catalog, str) and catalog.strip() else None
    schema_name = payload.get("schema")
    schema_name = (
        schema_name.strip() if isinstance(schema_name, str) and schema_name.strip() else None
    )

    raw_row_limit = payload.get("row_limit") or settings.sql.max_rows
    try:
        row_limit = max(1, min(int(raw_row_limit), int(sql_cfg.max_row_limit)))
    except TypeError, ValueError:
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "row_limit must be an integer.",
            },
        ) from None

    parameters = payload.get("parameters") or []
    if not isinstance(parameters, list):
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "parameters must be a JSON array.",
            },
        )

    wait_timeout_s = _parse_wait_timeout(
        payload.get("wait_timeout"),
        default_s=sql_cfg.default_wait_timeout_seconds,
        max_s=sql_cfg.max_wait_timeout_seconds,
    )
    on_wait_timeout = (payload.get("on_wait_timeout") or "CONTINUE").upper()
    if on_wait_timeout not in ("CONTINUE", "CANCEL"):
        raise _DbxApiError(
            400,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": "on_wait_timeout must be 'CONTINUE' or 'CANCEL'.",
            },
        )

    # Two preprocessing stages, both error-mapping to the DBX FAILED
    # envelope rather than HTTP 400 — DBX clients treat 400s as auth
    # / shape errors and surface them differently from FAILED rows.
    statement_id = str(uuid4())
    try:
        qualified = qualify_sql(
            statement_text,
            default_catalog=catalog,
            default_schema=schema_name,
        )
    except ParseError as exc:
        return JSONResponse(
            error_envelope(
                statement_id=statement_id,
                error_code="SQL_PARSE_ERROR",
                message=str(exc),
            )
        )
    try:
        prepared_sql = bind_parameters(qualified, parameters)
    except ParseError as exc:
        return JSONResponse(
            error_envelope(
                statement_id=statement_id,
                error_code="SQL_PARSE_ERROR",
                message=str(exc),
            )
        )
    except ValueError as exc:
        return JSONResponse(
            error_envelope(
                statement_id=statement_id,
                error_code="INVALID_PARAMETER_VALUE",
                message=str(exc),
            )
        )

    api_key_id = int(getattr(request.state, "api_key_id", 0) or 0)
    api_key_name = str(getattr(request.state, "api_key_name", "")) or "unknown"
    workspace_id = int(getattr(request.state, "workspace_id", 1) or 1)
    actor_email = effective_principal(request) or f"api_key:{api_key_name}"

    # per-key catalog ACL.  Runs after parse + qualify so
    # the AST walker sees the same fully-qualified table refs the
    # downstream UC enforcement sees.  Zero grants = unrestricted
    # (back-compat for every pre-120 key).
    settings_obj = getattr(request.app.state, "settings", None)
    enforce_catalog = (
        settings_obj is not None
        and getattr(settings_obj, "api_key_acl", None) is not None
        and bool(settings_obj.api_key_acl.enforce_catalog_grants)
        and api_key_id > 0
    )
    if enforce_catalog:
        from pointlessql.services.api_keys._acl import (
            check_catalog_allowed,
            load_catalog_grants_for,
        )
        from pointlessql.services.audit import _core as audit_core

        catalog_grants = load_catalog_grants_for(
            request.app.state.session_factory, api_key_id=api_key_id
        )
        result = check_catalog_allowed(
            catalog_grants,
            prepared_sql,
            default_catalog=catalog,
            default_schema=schema_name,
        )
        if not result.allowed:
            try:
                audit_core.log_action(
                    request.app.state.session_factory,
                    user_id=0,
                    user_email=actor_email,
                    action="api_key.access_denied.catalog",
                    target=f"api_key:{api_key_name}",
                    detail={
                        "catalog": result.denied_catalog,
                        "schema": result.denied_schema,
                        "key_name": api_key_name,
                    },
                    actor_role="system",
                    workspace_id=workspace_id,
                )
            except Exception:  # noqa: BLE001 — audit must never break auth
                logger.debug(
                    "Failed to emit api_key.access_denied.catalog audit",
                    exc_info=True,
                )
            return JSONResponse(
                error_envelope(
                    statement_id=statement_id,
                    error_code="PERMISSION_DENIED",
                    message=(
                        f"api key {api_key_name!r} is not granted access to "
                        f"{result.denied_catalog}.{result.denied_schema or '*'}"
                    ),
                )
            )

    _persist_pending(
        request,
        statement_id=statement_id,
        api_key_id=api_key_id,
        user_id=0,
        workspace_id=workspace_id,
        statement_text=statement_text,
        catalog=catalog,
        schema_name=schema_name,
        row_limit=row_limit,
    )

    # Per-statement execution timeout: take the smaller of the
    # editor-wide budget and the per-request wait window when the
    # client wants synchronous completion.  An async client (CONTINUE
    # on timeout) gets the full editor timeout for the background run.
    execution_timeout = int(settings.sql.query_timeout_seconds)

    task = asyncio.create_task(
        run_statement(
            request=request,
            statement_id=statement_id,
            sql_text=prepared_sql,
            row_limit=row_limit,
            timeout_seconds=execution_timeout,
            api_key_name=api_key_name,
            actor_email=actor_email,
        )
    )
    register_statement_task(request.app.state, statement_id, task)

    if wait_timeout_s <= 0:
        # Always-async path: return PENDING immediately, client polls.
        return JSONResponse(status_envelope(statement_id=statement_id, state="PENDING"))

    try:
        envelope = await asyncio.wait_for(asyncio.shield(task), timeout=wait_timeout_s)
        return JSONResponse(envelope)
    except TimeoutError:
        if on_wait_timeout == "CANCEL":
            cancel_statement(request.app.state, statement_id)
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except TimeoutError, asyncio.CancelledError, Exception:  # noqa: BLE001
                pass
            return JSONResponse(status_envelope(statement_id=statement_id, state="CANCELED"))
        # CONTINUE: leave task running, client polls.
        return JSONResponse(status_envelope(statement_id=statement_id, state="PENDING"))


def _row_to_envelope(row: SqlStatement) -> dict[str, Any]:
    """Reconstruct a DBX envelope from a persisted ``SqlStatement`` row.

    SUCCEEDED rows carry a gzipped manifest+result payload; failed /
    canceled rows just need the status-only envelope.
    """
    if row.status == "SUCCEEDED" and row.result_payload:
        return json.loads(gzip.decompress(row.result_payload).decode("utf-8"))
    return status_envelope(
        statement_id=row.statement_id,
        state=row.status,
        error_code=row.error_code,
        error_message=row.error_message,
    )


@router.get("/api/2.0/sql/statements/{statement_id}")
@_wrap_dbx
async def poll_statement(
    request: Request,
    statement_id: str,
    _: None = Depends(require_sql_execute),
) -> JSONResponse:
    """Return the current state of an in-flight or completed statement.

    Returns the persisted row's envelope.  Polls don't long-poll in
    v1 — clients sleep+retry.

    Args:
        request: Incoming FastAPI request.
        statement_id: Public statement handle.

    Returns:
        DBX-shape :class:`JSONResponse`.

    Raises:
        _DbxApiError: With status 404 when no row exists, 503 when
            the API is disabled.
    """
    _require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise _DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"Statement {statement_id!r} not found or expired.",
            },
        )
    return JSONResponse(_row_to_envelope(row))


@router.get("/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_index}")
@_wrap_dbx
async def fetch_chunk(
    request: Request,
    statement_id: str,
    chunk_index: int,
    _: None = Depends(require_sql_execute),
) -> JSONResponse:
    """Return one chunk of a SUCCEEDED statement's result.

    v1 always serialises a single chunk (``chunk_index=0`` returns
    the full result); any other index returns 404.

    Args:
        request: Incoming FastAPI request.
        statement_id: Public statement handle.
        chunk_index: Zero-based chunk index.

    Returns:
        DBX-shape chunk payload as :class:`JSONResponse`.

    Raises:
        _DbxApiError: 404 when the statement is missing or the
            chunk_index is out of range, 409 when the statement
            has not SUCCEEDED, 503 when the API is disabled.
    """
    _require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise _DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"Statement {statement_id!r} not found or expired.",
            },
        )
    if row.status != "SUCCEEDED" or not row.result_payload:
        raise _DbxApiError(
            409,
            {
                "error_code": "INVALID_PARAMETER_VALUE",
                "message": (
                    f"Statement {statement_id!r} is in state {row.status!r}; "
                    f"no result chunks are available."
                ),
            },
        )
    if chunk_index != 0:
        raise _DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": (
                    f"chunk_index={chunk_index} is out of range; v1 returns a single chunk."
                ),
            },
        )
    envelope = json.loads(gzip.decompress(row.result_payload).decode("utf-8"))
    return JSONResponse(envelope.get("result", {}))


@router.post("/api/2.0/sql/statements/{statement_id}/cancel")
@_wrap_dbx
async def cancel_statement_route(
    request: Request,
    statement_id: str,
    _: None = Depends(require_sql_execute),
) -> JSONResponse:
    """Request cancellation of an in-flight statement.

    Sets the ``cancel_requested`` flag and best-effort interrupts the
    DuckDB connection.  Already-terminal statements no-op (returning
    their current envelope) so duplicate cancel requests are safe.

    Args:
        request: Incoming FastAPI request.
        statement_id: Public statement handle.

    Returns:
        DBX-shape CANCELED envelope (or the current envelope when
        the statement was already terminal).

    Raises:
        _DbxApiError: 404 when no row exists for this id, 503 when
            the API is disabled.
    """
    _require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise _DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"Statement {statement_id!r} not found or expired.",
            },
        )
    if row.status in ("SUCCEEDED", "FAILED", "CANCELED"):
        return JSONResponse(_row_to_envelope(row))

    # Set the flag persistently before invoking interrupt so an
    # observer (e.g. retention sweep, audit reader) sees a coherent
    # state even if the in-process registry has already cleared.
    with factory() as session:
        session.execute(
            update(SqlStatement)
            .where(SqlStatement.statement_id == statement_id)
            .values(cancel_requested=True)
        )
        session.commit()
    cancel_statement(request.app.state, statement_id)
    return JSONResponse(status_envelope(statement_id=statement_id, state="CANCELED"))
