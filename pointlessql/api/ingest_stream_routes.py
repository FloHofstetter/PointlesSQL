"""Direct-write stream API — JSON events into Delta tables.

A Zerobus-style ingestion surface: producers POST small JSON row
batches at ``/api/ingest/streams/{catalog}/{schema}/{table}`` and the
rows land in the target Delta table through the in-process
:class:`pointlessql.services.ingest.stream_buffer.StreamBuffer`
(micro-batched by size and age, schema evolving additively).  A
companion ``/flush`` endpoint forces the pending batch out for
producers that need read-your-writes at batch boundaries.

Every request is authenticated and gated on ``MODIFY`` for the target
table (same handshake as the SQL write plane); the target must
already exist in the catalog — the stream API never creates tables.
Audit rows carry row *counts* only, never payloads.

This router is exported but not yet registered on the app — wiring it
into the route table (plus a lifespan shutdown hook for the buffer)
happens with the feature flag in the main session.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_uc_client, get_user, require_user
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.services.authorization import MODIFY, check_privilege
from pointlessql.services.ingest.stream_buffer import StreamBuffer, get_stream_buffer

router = APIRouter(tags=["ingest", "streams"])

# Per-request row cap — protects the event loop from megabatch JSON
# bodies; producers with more rows simply send more requests.
MAX_ROWS_PER_REQUEST = 1000


async def _resolve_stream_target(
    request: Request, catalog: str, schema: str, table: str
) -> tuple[str, str]:
    """Authenticate, authorise, and resolve the stream target.

    Mirrors the SQL dispatcher's MODIFY handshake
    (:func:`pointlessql.api.sql._dispatcher._privilege.enforce_modify_target`)
    minus the create-new-table branch — the stream API only writes to
    tables that already exist in the catalog.

    An anonymous request or a caller without ``MODIFY`` propagates
    :class:`AuthorizationError` from ``require_user`` /
    ``check_privilege``.

    Args:
        request: Incoming FastAPI request.
        catalog: Catalog name from the URL.
        schema: Schema name from the URL.
        table: Table name from the URL.

    Returns:
        ``(full_name, storage_location)`` for the target table.

    Raises:
        ResourceNotFoundError: When the table does not exist or has
            no registered storage location.
    """
    require_user(request)
    user = get_user(request)
    uc_client = get_uc_client(request)
    full_name = f"{catalog}.{schema}.{table}"
    info = await uc_client.get_table(catalog, schema, table)
    if not info:
        raise ResourceNotFoundError(f"Table not found: {full_name!r}")
    storage = info.get("storage_location")
    if not isinstance(storage, str) or not storage:
        raise ResourceNotFoundError(
            f"Table {full_name!r} has no storage_location on soyuz-catalog."
        )
    await check_privilege(
        uc_client, user["email"], bool(user.get("is_admin")), "table", full_name, MODIFY
    )
    return full_name, storage


def _validated_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and shape-check the ``rows`` list from the body.

    Args:
        body: Parsed JSON request body.

    Returns:
        The validated list of row dicts.

    Raises:
        ValidationError: When ``rows`` is missing/empty/not a list,
            exceeds :data:`MAX_ROWS_PER_REQUEST`, or contains a
            non-object entry.
    """
    raw = body.get("rows")
    if not isinstance(raw, list) or not raw:
        raise ValidationError("body must carry a non-empty 'rows' list of objects.")
    raw_rows = cast("list[Any]", raw)
    if len(raw_rows) > MAX_ROWS_PER_REQUEST:
        raise ValidationError(
            f"rows is capped at {MAX_ROWS_PER_REQUEST} per request, got {len(raw_rows)}."
        )
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            raise ValidationError(f"rows[{idx}] must be a JSON object.")
        rows.append(cast("dict[str, Any]", row))
    return rows


@router.post("/api/ingest/streams/{catalog}/{schema}/{table}")
async def api_stream_append(
    request: Request,
    catalog: str,
    schema: str,
    table: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Accept a batch of JSON rows for the target Delta table.

    Rows are buffered in-process and flushed as one Delta append when
    the buffer's size or age policy trips (or on ``/flush``).  A
    ``buffered`` value of ``0`` in the response means this request
    itself tripped the size flush.

    Args:
        request: Incoming FastAPI request.
        catalog: Catalog name from the URL.
        schema: Schema name from the URL.
        table: Table name from the URL.
        body: ``{"rows": [{...}, ...]}`` — at most
            :data:`MAX_ROWS_PER_REQUEST` objects.

    Returns:
        ``{"accepted": <rows in this request>, "buffered": <rows
        still pending for the target>}``.
    """
    rows = _validated_rows(body)
    full_name, storage = await _resolve_stream_target(request, catalog, schema, table)
    buffer: StreamBuffer = get_stream_buffer(request.app)
    buffered = await buffer.append(full_name, storage, rows)
    await audit(
        request,
        "ingest_stream.appended",
        f"table:{full_name}",
        {"rows": len(rows), "buffered": buffered},
    )
    return {"accepted": len(rows), "buffered": buffered}


@router.post("/api/ingest/streams/{catalog}/{schema}/{table}/flush")
async def api_stream_flush(
    request: Request,
    catalog: str,
    schema: str,
    table: str,
) -> dict[str, Any]:
    """Force-flush the target's pending rows to Delta.

    Args:
        request: Incoming FastAPI request.
        catalog: Catalog name from the URL.
        schema: Schema name from the URL.
        table: Table name from the URL.

    Returns:
        ``{"flushed": <rows written>}`` — ``0`` when nothing was
        pending.
    """
    full_name, _storage = await _resolve_stream_target(request, catalog, schema, table)
    buffer: StreamBuffer = get_stream_buffer(request.app)
    flushed = await buffer.flush(full_name)
    await audit(
        request,
        "ingest_stream.flushed",
        f"table:{full_name}",
        {"rows": flushed},
    )
    return {"flushed": flushed}
