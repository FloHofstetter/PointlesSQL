"""Table row-preview + stats endpoints.

Backs the table-detail card.  The preview endpoint resolves
``effective_permissions`` once and feeds ``check_privilege_from_effective``
(SELECT); rows go out with ``Cache-Control: no-store`` so revoked grants do
not leak through the browser disk cache, and classified columns are masked
server-side before serialisation.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from pointlessql.api._consumption_hook import enforce_consumption_for_read
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_authoring_product,
    get_uc_client,
    get_user,
)
from pointlessql.config import Settings
from pointlessql.services import governance as governance_service
from pointlessql.services.authorization import (
    SELECT,
    check_privilege_from_effective,
)
from pointlessql.services.pii._redactor import get_or_create_pii_hash_secret
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
from pointlessql.types import TableFqn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["catalog"])

PREVIEW_ROW_LIMIT = 10


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
    from pointlessql.pql import PQL

    try:
        client = (
            make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
        )
        pql = PQL(client=client, settings=settings)
        frame = pql.table(full_name)
        df = preview_head(frame, PREVIEW_ROW_LIMIT + 1)
    except Exception as exc:  # noqa: BLE001 — degrade preview card
        logger.exception("table preview failed for %s", full_name)
        detail, kind = humanize_preview_error(exc)
        return {"error": "preview_unavailable", "detail": detail, "kind": kind}
    truncated = len(df) > PREVIEW_ROW_LIMIT
    df = df.head(PREVIEW_ROW_LIMIT)
    columns = [str(c) for c in df.columns]
    rows = df.values.tolist()
    return jsonable_encoder({"columns": columns, "rows": rows, "truncated": truncated})


def _mask_preview_payload(
    request: Request,
    *,
    catalog: str,
    schema: str,
    table: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply column-classification masking to a preview payload.

    The governance sidecar at the catalog-preview access point: when the
    previewed table belongs to a data product with classified columns
    and the viewer is neither admin nor the product steward, masks the
    classified columns before the rows leave the server.  Tables outside
    a product, or with no classifications, pass through untouched.
    """
    if "rows" not in payload or "columns" not in payload:
        return payload
    factory = request.app.state.session_factory
    class_index = governance_service.classifications_for_schema(
        factory, catalog=catalog, schema=schema
    )
    strategies = {
        column: strategy for (tbl, column), (_cls, strategy) in class_index.items() if tbl == table
    }
    if not strategies:
        return payload

    from sqlalchemy import select  # noqa: PLC0415

    from pointlessql.models import DataProduct  # noqa: PLC0415

    user = get_user(request)
    workspace_id = current_workspace_id(request)
    with factory() as session:
        product = session.scalar(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        )
        is_steward = (
            product is not None
            and product.steward_user_id is not None
            and product.steward_user_id == user["id"]
        )
    unmask = governance_service.viewer_sees_clear(
        is_admin=bool(user.get("is_admin")), is_steward=is_steward
    )
    if unmask:
        return payload
    secret = get_or_create_pii_hash_secret(factory)
    payload["rows"] = governance_service.mask_sql_rows(
        payload["columns"], payload["rows"], strategies, unmask=False, secret=secret
    )
    return payload


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/preview")
async def api_table_preview(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    authoring_product_id: int | None = Depends(get_authoring_product),
) -> Response:
    """Return up to 10 rows from a Delta table as JSON.

    The row limit is fixed at 10 server-side — no client-tunable
    query param, to keep one fewer attack surface. Response carries
    ``Cache-Control: no-store`` so row data does not sit in the
    browser disk cache after a permission revocation.
    """
    client = get_uc_client(request)
    user = get_user(request)
    full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
    enforce_consumption_for_read(
        request,
        factory=request.app.state.session_factory,
        workspace_id=current_workspace_id(request),
        user=user,
        authoring_product_id=authoring_product_id,
        source_fqn=full_name,
    )
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
    payload = _mask_preview_payload(
        request,
        catalog=catalog_name,
        schema=schema_name,
        table=table_name,
        payload=payload,
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


@router.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/stats")
async def api_table_stats(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> Response:
    """Return per-column statistics for a Delta table as JSON.

    Used by the Phase-91 ``pql_describe_columns_with_stats`` chat
    tool: the LLM calls this before drafting SQL so the prompt
    carries row counts, nullability, cardinality, and a few
    extremes / modes per column.

    The reduction lives in
    :func:`pointlessql.services.column_stats.compute_table_stats`
    and is cached per ``(principal, fqn)`` for 5 minutes so a
    multi-turn refinement loop only scans the table once.  Auth
    re-uses the SELECT privilege gate the preview endpoint above
    enforces — describing a table you cannot read leaks shape
    information and is treated identically to reading rows.
    """
    from pointlessql.services.column_stats import compute_table_stats

    client = get_uc_client(request)
    user = get_user(request)
    full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
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
        compute_table_stats,
        settings,
        principal,
        full_name,
    )
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Cache-Control": "no-store"},
    )
