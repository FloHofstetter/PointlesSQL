"""``POST /api/sql/vector_search`` — top-K semantic search route.

Reuses :func:`enforce_select_per_table` from the SQL dispatcher so a
caller can vector-search a table iff they could ``SELECT`` it.  The
actual search runs through :func:`pointlessql.pql._vector.search`,
materialised on a thread so the event loop keeps serving.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api._audit_helpers import audit, record_query_async
from pointlessql.api.dependencies import effective_principal, get_user
from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table
from pointlessql.api.sql._dispatcher._types import DispatchContext
from pointlessql.api.sql.vector_search._models import (
    VectorSearchHit,
    VectorSearchRequest,
    VectorSearchResponse,
)
from pointlessql.exceptions import SQLExecutionError
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._vector import search as _pql_vector_search
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
from pointlessql.types import QueryStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql", "vector-search"])


@router.post("/api/sql/vector_search", response_model=VectorSearchResponse)
async def api_sql_vector_search(
    request: Request, body: VectorSearchRequest
) -> VectorSearchResponse:
    """Run a top-K semantic search against an existing vector index.

    Args:
        request: Incoming FastAPI request.
        body: Validated request body with ``table``, ``column``,
            ``query``, ``top_k``.

    Returns:
        A :class:`VectorSearchResponse` carrying the index's
        embedder + freshness metadata plus the ranked hits.

    Raises:
        SQLExecutionError: When the SQL editor is disabled or the
            target table is not three-part qualified.
        AuthorizationError: When the caller lacks ``SELECT`` on the
            target table (raised by ``check_privilege``).
        CatalogNotFoundError: When the target table is unknown.
        FileNotFoundError: When no vector index exists for the
            ``(table, column)`` pair.
    """  # noqa: DOC502,DOC503
    settings = request.app.state.settings
    if not settings.sql.enabled:
        raise SQLExecutionError("The SQL editor is disabled on this deployment.")

    parse_full_name(body.table)
    user = get_user(request)
    actor_email = effective_principal(request) or user.get("email", "")
    ctx = DispatchContext(
        request=request,
        settings=settings,
        sql=f"-- pql.vector_search({body.table}.{body.column})",
        ast=None,  # type: ignore[arg-type]  # privilege gate doesn't read AST
        stype=None,  # type: ignore[arg-type]
        actor_email=actor_email,
        is_admin=bool(user.get("is_admin", False)),
        conn=None,
        max_rows=settings.sql.max_rows,
    )
    await enforce_select_per_table(ctx, [body.table])

    principal = effective_principal(request)
    if principal:
        client = make_principal_client(settings, principal)
    else:
        client = make_soyuz_client(settings)
    unreachable_msg = f"soyuz-catalog at {settings.soyuz.catalog_url} is unreachable."

    started_at = datetime.now(UTC)
    try:
        result = await asyncio.to_thread(
            _pql_vector_search,
            client=client,
            table=body.table,
            column=body.column,
            query=body.query,
            top_k=body.top_k,
            unreachable_msg=unreachable_msg,
        )
    except FileNotFoundError as exc:
        finished_at = datetime.now(UTC)
        await record_query_async(
            request,
            sql_text=ctx.sql,
            started_at=started_at,
            finished_at=finished_at,
            status=QueryStatus.FAILED,
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[body.table],
            error_message=str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        finished_at = datetime.now(UTC)
        await record_query_async(
            request,
            sql_text=ctx.sql,
            started_at=started_at,
            finished_at=finished_at,
            status=QueryStatus.FAILED,
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[body.table],
            error_message=repr(exc),
        )
        raise
    finished_at = datetime.now(UTC)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    await record_query_async(
        request,
        sql_text=ctx.sql,
        started_at=started_at,
        finished_at=finished_at,
        status=QueryStatus.SUCCEEDED,
        row_count=len(result["hits"]),
        duration_ms=duration_ms,
        referenced_tables=[body.table],
    )
    audit_metadata: dict[str, Any] = {
        "table": body.table,
        "column": body.column,
        "top_k": body.top_k,
        "duration_ms": duration_ms,
        "model": result.get("model"),
        "embedder": result.get("embedder"),
    }
    await audit(request, "sql.vector_search", body.table, audit_metadata)

    return VectorSearchResponse(
        table=body.table,
        column=body.column,
        model=str(result.get("model") or ""),
        embedder=str(result.get("embedder") or ""),
        metric=str(result.get("metric") or "cosine"),
        delta_version_indexed=int(result.get("delta_version_indexed") or 0),
        hits=[VectorSearchHit(**h) for h in result["hits"]],
    )
