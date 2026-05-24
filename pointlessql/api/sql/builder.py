"""Visual Query Builder routes.

Three thin endpoints that wrap :mod:`pointlessql.services.sql.builder`:

* ``POST /api/sql/builder/columns`` — probe a 3-part table for its
  column names + DuckDB types (uses an existing ``SELECT * LIMIT 0``
  against the Delta view).
* ``POST /api/sql/builder/build`` — render builder state to SQL.
* ``POST /api/sql/builder/parse`` — best-effort the inverse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_user,
)
from pointlessql.exceptions import (
    CatalogNotFoundError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.sql.builder import (
    SUPPORTED_AGGS,
    SUPPORTED_OPS,
    build_sql_from_state,
    parse_sql_to_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql", "builder"])


@router.get("/api/sql/builder/operators")
async def api_builder_operators(request: Request) -> dict[str, Any]:
    """Return the supported operators + aggregate functions.

    Args:
        request: Incoming FastAPI request (auth-gated).

    Returns:
        ``{"operators": [...], "aggregates": [...]}``.
    """
    require_user(request)
    return {"operators": list(SUPPORTED_OPS), "aggregates": list(SUPPORTED_AGGS)}


@router.post("/api/sql/builder/columns")
async def api_builder_columns(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Probe a 3-part UC table for column names + DuckDB types.

    Args:
        request: Incoming request.
        body: ``{"table_fqn": "<catalog>.<schema>.<table>"}``.

    Returns:
        ``{"columns": [{"name": ..., "type": ...}, ...]}``.

    Raises:
        CatalogNotFoundError: When the table or its storage
            location is unknown.
        SQLExecutionError: When the underlying DuckDB probe fails.
    """  # noqa: DOC502,DOC503 — propagated from soyuz facade / DuckDB
    import duckdb

    from pointlessql.pql.engine import register_delta_view

    require_user(request)
    payload = body or {}
    table_fqn = str(payload.get("table_fqn") or "").strip()
    parts = table_fqn.split(".")
    if len(parts) != 3:
        raise ValidationError(
            "table_fqn must be three-part (catalog.schema.table)."
        )

    uc_client = get_uc_client(request)
    info = await uc_client.get_table(parts[0], parts[1], parts[2])
    if not info:
        raise CatalogNotFoundError(f"Table not found: {table_fqn!r}")
    storage = info.get("storage_location")
    if not isinstance(storage, str) or not storage:
        raise CatalogNotFoundError(
            f"Table {table_fqn!r} has no storage_location on soyuz-catalog."
        )
    user = get_user(request)
    actor = effective_principal(request) or user.get("email", "")
    await check_privilege(
        uc_client,
        actor,
        bool(user.get("is_admin", False)),
        "table",
        table_fqn,
        SELECT,
    )

    def _probe() -> list[dict[str, str]]:
        conn = duckdb.connect()
        try:
            register_delta_view(conn, table_fqn, storage)
            try:
                # quote each three-part segment so DuckDB treats it
                # as a single bound view name (PQL.autoload registers
                # the view under the full dotted alias).
                quoted = ".".join([f'"{p}"' for p in parts])
                arrow = conn.execute(f"SELECT * FROM {quoted} LIMIT 0").to_arrow_table()
            except duckdb.Error as exc:
                raise SQLExecutionError(
                    f"DuckDB rejected probe of {table_fqn!r}: {exc}"
                ) from exc
            from typing import cast as _cast

            arr = _cast(Any, arrow)
            return [
                {
                    "name": str(name),
                    "type": str(arr.schema.field(name).type),
                }
                for name in arr.column_names
            ]
        finally:
            conn.close()

    columns = await asyncio.to_thread(_probe)
    return {"columns": columns}


@router.post("/api/sql/builder/build")
async def api_builder_build(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Render a builder state dict into SELECT SQL.

    Args:
        request: Incoming request.
        body: A state dict — see
            :func:`pointlessql.services.sql.builder.build_sql_from_state`.

    Returns:
        ``{"sql": "..."}``.

    Raises:
        ValidationError: When the state is malformed.
    """  # noqa: DOC502 — raised via the service layer's ValueError → ValidationError shim
    require_user(request)
    state = body or {}
    try:
        sql = await asyncio.to_thread(build_sql_from_state, state)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return {"sql": sql}


@router.post("/api/sql/builder/parse")
async def api_builder_parse(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Best-effort parse a SELECT into builder state.

    Args:
        request: Incoming request.
        body: ``{"sql": "..."}``.

    Returns:
        ``{"state": {...} | null}``.  ``state`` is ``null`` when the
        SQL falls outside the builder's supported subset.
    """
    require_user(request)
    sql = str((body or {}).get("sql") or "")
    if not sql.strip():
        return {"state": None}
    state = await asyncio.to_thread(parse_sql_to_state, sql)
    return {"state": state}
