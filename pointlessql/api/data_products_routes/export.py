"""Parquet file-export output port for a data product.

``GET /api/data-products/{catalog}/{schema}/export?table={t}`` streams
one declared table as a Parquet file — the working realisation of a
``file`` output port (B1).  It reuses the SELECT-privilege gate the
table-preview endpoint uses, so a consumer can only export tables they
may read.  Only tables the product *declares* in its contract are
exportable, so the port never leaks an undeclared sibling table.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_uc_client,
    get_user,
    require_user,
)
from pointlessql.config import Settings
from pointlessql.exceptions import BadRequestError
from pointlessql.services import governance as governance_service
from pointlessql.services.authorization import SELECT, check_privilege_from_effective
from pointlessql.services.pii._redactor import get_or_create_pii_hash_secret
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client

router = APIRouter(tags=["data-products"])


def _frame_to_parquet(frame: Any) -> bytes:
    """Serialise an engine frame to Parquet bytes.

    Handles the pandas default plus pyarrow / polars frames; converts
    via pyarrow as the common target when the frame isn't pandas.

    Args:
        frame: The engine-native frame returned by ``pql.table``.

    Returns:
        The Parquet file payload as bytes.

    Raises:
        BadRequestError: When the frame type can't be serialised.
    """
    buffer = io.BytesIO()
    # pandas / polars expose ``to_parquet`` directly.
    if hasattr(frame, "to_parquet"):
        frame.to_parquet(buffer)
        return buffer.getvalue()
    # pyarrow Table.
    try:
        import pyarrow as pa  # noqa: PLC0415 — lazy, engine-optional
        import pyarrow.parquet as pq  # noqa: PLC0415

        if isinstance(frame, pa.Table):
            pq.write_table(frame, buffer)
            return buffer.getvalue()
        # duckdb relation → arrow → parquet.
        if hasattr(frame, "to_arrow_table"):
            pq.write_table(frame.to_arrow_table(), buffer)
            return buffer.getvalue()
    except ImportError:  # pragma: no cover — pyarrow ships with deltalake
        pass
    raise BadRequestError("data product table could not be serialised to Parquet")


@router.get("/api/data-products/{catalog}/{schema}/export")
async def export_table(
    catalog: str,
    schema: str,
    request: Request,
    table: str,
) -> StreamingResponse:
    """Stream one declared product table as a Parquet download.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        table: The table to export — must be declared in the product
            contract.

    Returns:
        A ``StreamingResponse`` carrying the Parquet payload with a
        ``Content-Disposition: attachment`` header.

    Raises:
        BadRequestError: When the table isn't declared on the product.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, contract, _e, _d = load_one(factory, workspace_id, catalog, schema)

    declared = {t.name for t in contract.tables}
    if table not in declared:
        raise BadRequestError(
            f"table {table!r} is not declared by data product {catalog}.{schema}"
        )

    full_name = f"{catalog}.{schema}.{table}"
    principal = effective_principal(request) or user.get("email", "")
    client = get_uc_client(request)
    effective = await client.get_effective_permissions("table", full_name)
    check_privilege_from_effective(
        effective,
        principal,
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )

    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    unmask = governance_service.viewer_sees_clear(
        is_admin=bool(user.get("is_admin")), is_steward=is_steward
    )
    class_index = governance_service.classifications_for_schema(
        factory, catalog=catalog, schema=schema
    )
    strategies = {
        column: strategy for (tbl, column), (_cls, strategy) in class_index.items() if tbl == table
    }
    secret = None if unmask else get_or_create_pii_hash_secret(factory)

    settings: Settings = request.app.state.settings
    payload = await asyncio.to_thread(
        _export_blocking, settings, principal, full_name, strategies, unmask, secret
    )
    headers = {"Content-Disposition": f'attachment; filename="{catalog}.{schema}.{table}.parquet"'}
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.apache.parquet",
        headers=headers,
    )


def _export_blocking(
    settings: Settings,
    principal: str,
    full_name: str,
    strategies: dict[str, str],
    unmask: bool,
    secret: str | None,
) -> bytes:
    """Read *full_name* via PQL, mask classified columns, serialise (blocking).

    The masking sidecar runs here, at the output port — a non-privileged
    consumer never receives cleartext for a classified column.
    """
    from pointlessql.pql import PQL

    client = (
        make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
    )
    pql = PQL(client=client, settings=settings)
    frame = pql.table(full_name)
    frame = governance_service.mask_dataframe(frame, strategies, unmask=unmask, secret=secret)
    return _frame_to_parquet(frame)
