"""``POST /api/sql/execute/{query_id}/cancel`` — interrupt a running query.

Looks up the live :class:`duckdb.DuckDBPyConnection` the execute
route parked in the per-app registry and calls ``.interrupt()``.
The execute route's worker thread observes the
:class:`duckdb.InterruptException` and the dispatcher folds it back
to a ``cancelled`` history row.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.sql.editor._helpers import live_queries

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql"])


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
        except Exception:  # noqa: BLE001 — diagnostic only
            logger.exception("conn.interrupt() raised on cancel")
    await audit(request, "query.cancelled", f"query_id:{query_id}", None)
    return Response(status_code=204)
