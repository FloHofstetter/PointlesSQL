"""Catalog tree API routes — /api/tree, /api/catalogs, schemas, tables, preview.

Sprint 86 split out of ``api/main.py``.  Owns the five JSON endpoints
the sidebar + breadcrumb navigation hits to walk the
catalog → schema → table tree, plus the row-preview endpoint that
backs the table-detail card.

Authorization model is the same as before: schema/table list use the
hierarchical ``check_privilege`` (USE_CATALOG, USE_SCHEMA), and the
preview endpoint resolves ``effective_permissions`` once and feeds
``check_privilege_from_effective(SELECT)``.  Preview rows go out
with ``Cache-Control: no-store`` so revoked grants do not leak
through the browser disk cache.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from pointlessql.api.dependencies import get_uc_client, get_user
from pointlessql.services.authorization import (
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    check_privilege,
    check_privilege_from_effective,
)
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["catalog"])

PREVIEW_ROW_LIMIT = 10


@router.get("/api/tree")
async def api_tree(request: Request) -> list[dict[str, object]]:
    """Return the full catalog/schema/table tree for the sidebar."""
    client = get_uc_client(request)
    return await client.get_tree()


@router.get("/api/catalogs")
async def api_catalogs(request: Request) -> list[dict[str, object]]:
    """Return all catalogs as JSON."""
    client = get_uc_client(request)
    return await client.list_catalogs()


@router.get("/api/catalogs/{catalog_name}/schemas")
async def api_schemas(request: Request, catalog_name: str) -> list[dict[str, object]]:
    """Return schemas inside a catalog as JSON."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        USE_CATALOG,
    )
    return await client.list_schemas(catalog_name)


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables")
async def api_tables(
    request: Request, catalog_name: str, schema_name: str,
) -> list[dict[str, object]]:
    """Return tables inside a schema as JSON."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "schema",
        f"{catalog_name}.{schema_name}",
        USE_SCHEMA,
    )
    return await client.list_tables(catalog_name, schema_name)


def preview_head(frame: Any, n: int) -> Any:
    """Return at most *n* rows of *frame* as a pandas DataFrame.

    Engine-aware: DuckDB relations expose ``limit``; polars frames
    expose ``to_pandas``; pandas stays untouched. Keeps DuckDB lazy
    instead of materialising the whole relation.

    Args:
        frame: Whatever :meth:`pointlessql.pql.pql.PQL.table` returned —
            a pandas/polars frame or a DuckDB relation.
        n: Maximum number of rows to return.

    Returns:
        A pandas DataFrame holding at most *n* rows.
    """
    import pandas as pd

    if hasattr(frame, "limit") and hasattr(frame, "df"):
        return frame.limit(n).df()
    if hasattr(frame, "head"):
        head = frame.head(n)
        if hasattr(head, "to_pandas"):
            return head.to_pandas()
        return head
    return pd.DataFrame(frame).head(n)


def run_table_preview(settings: Settings, principal: str, full_name: str) -> dict[str, Any]:
    """Read up to 10 rows of a Delta table and serialise them.

    Runs inside :func:`asyncio.to_thread` so the sync :class:`PQL`
    helper does not block the event loop. Degrades gracefully on any
    failure: a broken table must fail this card, not the page.

    Args:
        settings: Application settings (for soyuz URL + engine).
        principal: User email forwarded as ``X-Principal``. Empty
            string falls back to the anonymous client.
        full_name: Three-part table name ``catalog.schema.table``.

    Returns:
        Either ``{"columns": [...], "rows": [...], "truncated": bool}``
        on success, or ``{"error": "preview_unavailable", "detail":
        str}`` on failure.
    """
    from pointlessql.pql.pql import PQL

    try:
        client = (
            make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
        )
        pql = PQL(client=client, settings=settings)
        frame = pql.table(full_name)
        df = preview_head(frame, PREVIEW_ROW_LIMIT + 1)
    except Exception as exc:  # noqa: BLE001 — degrade preview card
        logger.warning("table preview failed for %s: %s", full_name, exc)
        return {"error": "preview_unavailable", "detail": str(exc)}
    truncated = len(df) > PREVIEW_ROW_LIMIT
    df = df.head(PREVIEW_ROW_LIMIT)
    columns = [str(c) for c in df.columns]
    rows = df.values.tolist()
    return jsonable_encoder({"columns": columns, "rows": rows, "truncated": truncated})


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/preview")
async def api_table_preview(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> Response:
    """Return up to 10 rows from a Delta table as JSON.

    The row limit is fixed at 10 server-side — no client-tunable
    query param, to keep one fewer attack surface. Response carries
    ``Cache-Control: no-store`` so row data does not sit in the
    browser disk cache after a permission revocation.
    """
    client = get_uc_client(request)
    user = get_user(request)
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    effective = await client.get_effective_permissions("table", full_name)
    check_privilege_from_effective(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    settings: Settings = request.app.state.settings
    payload = await asyncio.to_thread(
        run_table_preview, settings, user.get("email", ""), full_name,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})
