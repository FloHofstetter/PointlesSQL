"""Catalog tree API routes — /api/tree, /api/catalogs, schemas, tables, preview.

Owns the five JSON endpoints the sidebar + breadcrumb navigation hits
to walk the catalog → schema → table tree, plus the row-preview
endpoint that backs the table-detail card.

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
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
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
async def api_tree(
    request: Request,
    primary_only: bool = False,
) -> list[dict[str, object]]:
    """Return the full catalog/schema/table tree for the sidebar.

    When *primary_only* is ``True``, the result is filtered to the
    catalogs the active workspace has pinned (any pin mode counts).
    ``False`` (the default) keeps the legacy behaviour of returning
    every catalog visible to the UC client, so single-tenant installs
    see no behaviour change.

    The pin filter is purely cosmetic: queries against unpinned
    catalogs still work end-to-end via the SQL editor and pql
    primitives — this only shapes the sidebar tree's initial
    expansion.
    """
    client = get_uc_client(request)
    tree = await client.get_tree()
    if not primary_only:
        return tree
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return tree
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    from sqlalchemy import select

    from pointlessql.models import WorkspaceCatalogPin

    with factory() as session:
        pinned = {
            row.catalog_name
            for row in session.scalars(
                select(WorkspaceCatalogPin).where(WorkspaceCatalogPin.workspace_id == workspace_id)
            ).all()
        }
    if not pinned:
        return tree
    return [c for c in tree if isinstance(c, dict) and c.get("name") in pinned]


@router.get("/api/tree/search")
async def api_tree_search(request: Request, q: str, limit: int = 50) -> dict[str, object]:
    """Server-side substring search across the catalog tree.

    Returns the catalog/schema/table FQNs whose components match
    *q* case-insensitively.  Walks the tree once via the existing
    :meth:`UnityCatalogClient.get_tree` and filters in-memory; for
    >1000-table tenants this is significantly cheaper than shipping
    the entire payload to the browser and filtering with JS.

    The cap is hardcoded at *limit* to keep payloads bounded; if a
    user types something so generic that it matches >limit tables
    they should refine the query.

    Args:
        request: Incoming FastAPI request.
        q: Substring (case-insensitive).  Must be ≥ 2 chars.
        limit: Max matches (default 50, capped at 200).

    Returns:
        ``{matches: [{kind: catalog|schema|table, full_name, ...}]}``.

    Raises:
        ValidationError: When *q* is shorter than 2 chars.
    """
    from pointlessql.exceptions import ValidationError

    needle = q.strip().lower()
    if len(needle) < 2:
        raise ValidationError("query must be at least 2 characters")
    capped = min(max(1, limit), 200)

    client = get_uc_client(request)
    tree = await client.get_tree()

    matches: list[dict[str, object]] = []

    def _maybe_add(entry: dict[str, object]) -> bool:
        matches.append(entry)
        return len(matches) >= capped

    for catalog in tree:
        if not isinstance(catalog, dict):
            continue
        catalog_name = str(catalog.get("name") or "")
        if not catalog_name:
            continue
        if needle in catalog_name.lower():
            if _maybe_add({"kind": "catalog", "full_name": catalog_name}):
                break
        schemas_obj = catalog.get("schemas")
        if not isinstance(schemas_obj, list):
            continue
        for schema in schemas_obj:
            if not isinstance(schema, dict):
                continue
            schema_name = str(schema.get("name") or "")
            if not schema_name:
                continue
            schema_fqn = f"{catalog_name}.{schema_name}"
            if needle in schema_name.lower() and _maybe_add(
                {"kind": "schema", "full_name": schema_fqn}
            ):
                break
            tables_obj = schema.get("tables")
            if isinstance(tables_obj, list):
                for table in tables_obj:
                    if not isinstance(table, dict):
                        continue
                    table_name = str(table.get("name") or "")
                    if not table_name:
                        continue
                    if needle in table_name.lower():
                        if _maybe_add(
                            {
                                "kind": "table",
                                "full_name": f"{schema_fqn}.{table_name}",
                                "catalog": catalog_name,
                                "schema": schema_name,
                                "table": table_name,
                            }
                        ):
                            break
                if len(matches) >= capped:
                    break
            volumes_obj = schema.get("volumes")
            if isinstance(volumes_obj, list):
                for volume in volumes_obj:
                    if not isinstance(volume, dict):
                        continue
                    volume_name = str(volume.get("name") or "")
                    if not volume_name:
                        continue
                    if needle in volume_name.lower():
                        if _maybe_add(
                            {
                                "kind": "volume",
                                "full_name": f"{schema_fqn}.{volume_name}",
                                "catalog": catalog_name,
                                "schema": schema_name,
                                "volume": volume_name,
                            }
                        ):
                            break
                if len(matches) >= capped:
                    break
            models_obj = schema.get("models")
            if isinstance(models_obj, list):
                for model in models_obj:
                    if not isinstance(model, dict):
                        continue
                    model_name = str(model.get("name") or "")
                    if not model_name:
                        continue
                    if needle in model_name.lower():
                        if _maybe_add(
                            {
                                "kind": "model",
                                "full_name": f"{schema_fqn}.{model_name}",
                                "catalog": catalog_name,
                                "schema": schema_name,
                                "model": model_name,
                            }
                        ):
                            break
            if len(matches) >= capped:
                break
        if len(matches) >= capped:
            break

    return {"matches": matches, "truncated": len(matches) >= capped}


@router.get("/api/recents")
async def api_recents(request: Request) -> dict[str, object]:
    """Return the current user's most-recent table visits."""
    from pointlessql.services import recents as recents_service

    user = get_user(request)
    user_id = int(user.get("id", 0) or 0)
    factory = request.app.state.session_factory
    rows = recents_service.top_recent_tables(factory, user_id)
    return {"recents": rows}


@router.delete("/api/recents")
async def api_clear_recents(request: Request) -> dict[str, bool]:
    """Wipe the current user's recents block."""
    from sqlalchemy import delete

    from pointlessql.models import RecentTable

    user = get_user(request)
    user_id = int(user.get("id", 0) or 0)
    if user_id <= 0:
        return {"ok": True}
    factory = request.app.state.session_factory
    with factory() as session:
        session.execute(delete(RecentTable).where(RecentTable.user_id == user_id))
        session.commit()
    return {"ok": True}


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
    # Align the privilege check with get_uc_client — both must
    # respect ``X-Principal`` so a Hermes plugin call on behalf of
    # a real user is gated against that user's UC grants instead
    # of the api_key:<name> synthetic principal.
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        USE_CATALOG,
    )
    return await client.list_schemas(catalog_name)


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables")
async def api_tables(
    request: Request,
    catalog_name: str,
    schema_name: str,
) -> list[dict[str, object]]:
    """Return tables inside a schema as JSON."""
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "schema",
        f"{catalog_name}.{schema_name}",
        USE_SCHEMA,
    )
    return await client.list_tables(catalog_name, schema_name)


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}")
async def api_get_table(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> dict[str, object]:
    """Return one table's full metadata (columns + tags) as JSON.

    The ``hermes-plugin-pointlessql`` ``pql_get_table`` tool calls
    this endpoint to pull column types + UC tags + comment without
    scraping the HTML catalog browser. The shape is whatever
    soyuz-catalog returns for ``GET /tables/{full_name}``; the gate
    matches the schema-list route (USE_SCHEMA on the parent schema)
    since visibility of an individual table follows visibility of
    its schema.

    Args:
        request: Incoming FastAPI request.
        catalog_name: First part of the three-part name.
        schema_name: Second part.
        table_name: Third part.

    Returns:
        Soyuz-shaped table info dict.
    """
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "schema",
        f"{catalog_name}.{schema_name}",
        USE_SCHEMA,
    )
    return await client.get_table(catalog_name, schema_name, table_name)


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


def humanize_preview_error(exc: Exception) -> tuple[str, str | None]:
    """Translate a deltalake/duckdb preview failure into user-facing copy.

    The deltalake Python library propagates Rust-style errors verbatim,
    e.g. ``Invalid table location: file:///tmp/demo/orders Error:
    Os { code: 2, kind: NotFound, message: "No such file or
    directory" }``.  The card surfaces those raw and reads as API
    debug noise rather than something a user can act on.

    This helper classifies the most common failure and returns a
    one-line plain-English message plus a slug the frontend can use
    to render an actionable hint.  Unknown failures fall through to
    ``str(exc)`` so we never lose information.

    Args:
        exc: The exception raised inside :func:`run_table_preview`.

    Returns:
        ``(detail, kind)`` where ``detail`` is the message to render
        in place of the raw exception text, and ``kind`` is one of
        ``"missing_storage"`` or ``None`` (for the unknown bucket).
    """
    msg = str(exc)
    if "NotFound" in msg and "No such file or directory" in msg:
        path_match = re.search(r"file://(\S+?)(?:\s|$|/Error)", msg)
        path = path_match.group(1) if path_match else None
        if path:
            return (
                f"Table data is missing on disk: {path}. "
                "The catalog still points here but no files were found "
                "at that location.",
                "missing_storage",
            )
        return (
            "Table data is missing on disk. The catalog still points "
            "to a path that no longer exists.",
            "missing_storage",
        )
    return (msg, None)


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
        <friendly>, "kind": <slug | None>}`` on failure.  The
        ``detail`` is humanised by :func:`humanize_preview_error`;
        ``kind`` lets the frontend render an actionable hint.
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
        detail, kind = humanize_preview_error(exc)
        return {"error": "preview_unavailable", "detail": detail, "kind": kind}
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
    principal = effective_principal(request) or user.get("email", "")
    effective = await client.get_effective_permissions("table", full_name)
    check_privilege_from_effective(
        effective,
        principal,
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    settings: Settings = request.app.state.settings
    payload = await asyncio.to_thread(
        run_table_preview,
        settings,
        principal,
        full_name,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})
