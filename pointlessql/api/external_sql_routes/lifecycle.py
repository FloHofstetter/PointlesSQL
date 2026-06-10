"""Statement poll / chunk-fetch / cancel endpoints."""

from __future__ import annotations

import gzip
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update

from pointlessql.api._dbx_error_wrapper import (
    DbxApiError as DbxApiError,
)
from pointlessql.api._dbx_error_wrapper import (
    dbx_error_response as dbx_error_response,
)
from pointlessql.api._dbx_error_wrapper import (
    wrap_dbx as wrap_dbx,
)
from pointlessql.api.dependencies import require_sql_execute
from pointlessql.api.external_sql_routes._shared import require_enabled
from pointlessql.models import SqlStatement
from pointlessql.services.sql_statements import (
    cancel_statement,
    fetch_statement,
)
from pointlessql.services.sql_statements._envelope import status_envelope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql-statements"])


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
@wrap_dbx
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
        DbxApiError: With status 404 when no row exists, 503 when
            the API is disabled.
    """
    require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"Statement {statement_id!r} not found or expired.",
            },
        )
    return JSONResponse(_row_to_envelope(row))


@router.get("/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_index}")
@wrap_dbx
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
        DbxApiError: 404 when the statement is missing or the
            chunk_index is out of range, 409 when the statement
            has not SUCCEEDED, 503 when the API is disabled.
    """
    require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise DbxApiError(
            404,
            {
                "error_code": "RESOURCE_NOT_FOUND",
                "message": f"Statement {statement_id!r} not found or expired.",
            },
        )
    if row.status != "SUCCEEDED" or not row.result_payload:
        raise DbxApiError(
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
        raise DbxApiError(
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
@wrap_dbx
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
        DbxApiError: 404 when no row exists for this id, 503 when
            the API is disabled.
    """
    require_enabled(request)
    factory = request.app.state.session_factory
    row = fetch_statement(factory, statement_id)
    if row is None:
        raise DbxApiError(
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
