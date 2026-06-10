"""``GET /api/sql/execute/{history_id}/download`` — stream history result.

Re-runs a previously-recorded query (re-enforced!) and streams CSV
or Parquet.  A stale history row is *not* a bypass — grants can be
revoked after the original run, so every download re-runs the
``check_privilege(SELECT)`` loop the original execute did.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import effective_principal, get_uc_client, get_user
from pointlessql.api.sql.editor._helpers import run_sql_export_sync
from pointlessql.config import Settings
from pointlessql.services.authorization import SELECT, check_privilege

router = APIRouter(tags=["sql"])


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

    Propagates :class:`AuthorizationError` from
    :func:`check_privilege` when the caller lost ``SELECT`` on a
    referenced table since the original run.

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
    """
    import csv
    import io

    from fastapi.responses import StreamingResponse

    from pointlessql.exceptions import CatalogNotFoundError, SQLExecutionError
    from pointlessql.models import QueryHistory
    from pointlessql.pql import SQLParseError, prepare_sql

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
