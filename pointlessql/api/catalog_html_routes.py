"""Catalog browser HTML pages — catalog detail + schema detail + table detail.

Three pages drive the sidebar navigation: clicking a catalog opens
``/catalogs/{cat}``, clicking a schema opens ``/catalogs/{cat}/
schemas/{sch}``, clicking a table opens ``/catalogs/{cat}/schemas/
{sch}/tables/{tab}``.  Each page fetches metadata + tags +
permissions + effective-permissions concurrently from soyuz, then
hierarchical privilege checks gate the render
(USE_CATALOG → USE_SCHEMA → SELECT).

The corresponding JSON endpoints
(``/api/catalogs/{cat}/schemas`` etc.) live in
``api/catalog_routes.py``.  These HTML routes are the user-facing
twin: same enforcement, different output.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_uc_client,
    get_user,
)
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    check_privilege_from_effective,
    has_privilege,
)
from pointlessql.types import TableFqn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["catalog-html"])


@router.get("/catalogs/{catalog_name}", response_class=HTMLResponse)
async def catalog_detail(request: Request, catalog_name: str) -> HTMLResponse:
    """Render metadata for a single catalog."""
    client = get_uc_client(request)
    user = get_user(request)
    catalog: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    schemas: list[dict[str, Any]] = []
    error: str | None = None
    try:
        catalog, tags, permissions, effective, schemas = await asyncio.gather(
            client.get_catalog(catalog_name),
            client.get_tags("catalog", catalog_name),
            client.get_permissions("catalog", catalog_name),
            client.get_effective_permissions("catalog", catalog_name),
            client.list_schemas(catalog_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    # Enforce after gather so we reuse the effective permissions data.
    # AuthorizationError propagates to the centralized handler → 403.html.
    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "catalog",
            catalog_name,
            USE_CATALOG,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )

    # Load sync history for foreign catalogs so the history card has
    # something to render. Managed catalogs never sync, so we skip the
    # DB hit entirely.
    sync_runs: list[Any] = []
    if (
        error is None
        and catalog is not None
        and catalog.get("connection_name")
        and user.get("is_admin", False)
    ):
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None:
            sync_runs = pg_sync_service.list_recent_runs(factory, catalog_name)

    return get_templates(request).TemplateResponse(
        request,
        "pages/schemas.html",
        {
            "catalog_name": catalog_name,
            "catalog": catalog,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "can_manage": can_manage,
            "sync_runs": sync_runs,
            "schemas": schemas,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}",
    response_class=HTMLResponse,
)
async def schema_detail(request: Request, catalog_name: str, schema_name: str) -> HTMLResponse:
    """Render metadata for a single schema."""
    client = get_uc_client(request)
    user = get_user(request)
    schema: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}"
    try:
        schema, tags, permissions, effective, tables = await asyncio.gather(
            client.get_schema(catalog_name, schema_name),
            client.get_tags("schema", full_name),
            client.get_permissions("schema", full_name),
            client.get_effective_permissions("schema", full_name),
            client.list_tables(catalog_name, schema_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "schema",
            full_name,
            USE_SCHEMA,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    return get_templates(request).TemplateResponse(
        request,
        "pages/tables.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "schema": schema,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "tables": tables,
            "can_manage": can_manage,
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": None,
        },
    )


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}",
    response_class=HTMLResponse,
)
async def table_detail(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> HTMLResponse:
    """Render metadata and column schema for a single table."""
    client = get_uc_client(request)
    user = get_user(request)
    table: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    lineage: dict[str, Any] = {}
    error: str | None = None
    full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
    try:
        table, tags, permissions, effective, lineage = await asyncio.gather(
            client.get_table(catalog_name, schema_name, table_name),
            client.get_tags("table", full_name),
            client.get_permissions("table", full_name),
            client.get_effective_permissions("table", full_name),
            client.get_lineage(full_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "table",
            full_name,
            SELECT,
        )
        # record the visit for the per-user "Recent
        # tables" sidebar block.  Best-effort; service swallows its
        # own exceptions so a recents-write hiccup never blocks the
        # rendered page.
        from pointlessql.services import recents as recents_service

        recents_service.record_table_visit(
            request.app.state.session_factory,
            int(user.get("id", 0) or 0),
            full_name,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    lineage_columns = _columns_with_lineage(full_name)
    external_producers = _external_producers_for_table(
        full_name, session_factory=request.app.state.session_factory
    )
    workspace_id = current_workspace_id(request)
    cdf_subscription = _cdf_subscription_for_table(
        full_name,
        workspace_id=workspace_id,
        session_factory=request.app.state.session_factory,
    )
    cdf_recent_events = (
        _cdf_recent_events_for_table(
            full_name,
            workspace_id=workspace_id,
            session_factory=request.app.state.session_factory,
        )
        if cdf_subscription is not None
        else []
    )
    vector_indices = _vector_indices_for_table(
        catalog_name,
        schema_name,
        table_name,
        workspace_id=workspace_id,
        session_factory=request.app.state.session_factory,
    )
    # text columns the user can pick from the
    # "Semantic search" tab's empty-state create-index form.
    # Filter to STRING / VARCHAR-shaped types so the dropdown does
    # not offer numeric columns that the embedder cannot handle.
    # ``table`` is a dict here (the UC-facade-shaped row) — its
    # ``columns`` entry is a list of column dicts with ``name`` +
    # ``type_text`` keys.  ``[]`` is the empty-page fallback when the
    # catalog call errored above.
    _cols = (table or {}).get("columns", []) if isinstance(table, dict) else []
    text_column_names = [
        col["name"]
        for col in _cols
        if _is_text_column_type(col.get("type_text", ""))
    ]
    return get_templates(request).TemplateResponse(
        request,
        "pages/table.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "table": table,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "lineage": lineage,
            "lineage_columns": lineage_columns,
            "external_producers": external_producers,
            "cdf_subscription": cdf_subscription,
            "cdf_recent_events": cdf_recent_events,
            "vector_indices": vector_indices,
            "text_column_names": text_column_names,
            "can_manage": can_manage,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )


_TEXT_TYPE_PREFIXES: tuple[str, ...] = ("STRING", "VARCHAR", "CHAR", "TEXT")


def _is_text_column_type(type_text: str) -> bool:
    """Whether *type_text* is a text-shaped column type.

    Phase 92 vector-index create-form dropdown filters by this so the
    user cannot pick a numeric column.  The check is intentionally
    permissive: it matches by prefix to handle ``VARCHAR(200)`` etc.
    """
    if not type_text:
        return False
    upper = type_text.strip().upper()
    return any(upper.startswith(prefix) for prefix in _TEXT_TYPE_PREFIXES)


def _vector_indices_for_table(
    catalog: str,
    schema: str,
    table: str,
    *,
    workspace_id: int,
    session_factory: Any,
) -> list[dict[str, Any]]:
    """Return the workspace's vector indices on *table* as plain dicts.

    Best-effort: returns an empty list when the metadata DB is
    unreachable so a transient DB hiccup never breaks the table page.
    """
    if session_factory is None:
        return []
    try:
        from pointlessql.models.vector import VectorIndex

        with session_factory() as session:
            rows = list(
                session.query(VectorIndex)
                .filter_by(
                    workspace_id=workspace_id,
                    catalog=catalog,
                    schema=schema,
                    table=table,
                )
                .order_by(VectorIndex.column)
                .all()
            )
    except Exception:  # noqa: BLE001 — page renders even when DB is unhappy
        # bare-broad-ok: DB miss must not break table-detail HTML render
        logger.exception(
            "vector_indexes_for_table failed catalog=%s schema=%s table=%s",
            catalog,
            schema,
            table,
        )
        return []
    return [
        {
            "id": r.id,
            "column": r.column,
            "dim": r.dim,
            "model": r.model,
            "embedder": r.embedder,
            "metric": r.metric,
            "delta_version_indexed": r.delta_version_indexed,
            "last_built_at": r.last_built_at.isoformat() if r.last_built_at else None,
            "last_built_rows": r.last_built_rows,
            "last_error": r.last_error,
        }
        for r in rows
    ]


def _columns_with_lineage(full_name: str) -> set[str]:
    """Return the set of column names in *full_name* that have a column-edge row.

    drives the table-detail page's "lineage" link
    per column.  Best-effort: a missing metadata DB or schema drift
    yields an empty set so the link silently disappears rather than
    raising.

    Args:
        full_name: Three-part UC name of the table.

    Returns:
        Set of distinct ``target_column`` values from
        ``lineage_column_map`` for this table.
    """
    try:
        from sqlalchemy import select as _select

        from pointlessql.db import get_session_factory
        from pointlessql.models import LineageColumnMap

        factory = get_session_factory()
        with factory() as session:
            stmt = (
                _select(LineageColumnMap.target_column)
                .where(LineageColumnMap.target_table == full_name)
                .distinct()
            )
            return {str(row[0]) for row in session.execute(stmt).all()}
    except Exception:  # noqa: BLE001 — best-effort badge population
        # bare-broad-ok: catalog page must not block on metadata-DB hiccup
        return set()


def _external_producers_for_table(full_name: str, *, session_factory: Any) -> list[dict[str, Any]]:
    """Return the Phase-40 external producers writing into *full_name*.

    Walks ``lineage_column_map`` for rows with ``producer IS NOT NULL``
    targeting *full_name*, groups by producer, and returns one row per
    producer with the distinct source-table list and the latest
    ``created_at``.  Used by the table-detail "External producers"
    block on the lineage card.

    Best-effort: a DB hiccup or schema drift yields an empty list so
    a federation-not-set-up install still renders the page cleanly.

    Args:
        full_name: Three-part UC name of the table.
        session_factory: SQLAlchemy session factory bound to the
            metadata DB.  Threaded in by the route so unit tests
            can pass the conftest-built factory directly.

    Returns:
        List of ``{producer, source_tables, last_seen_at}`` dicts,
        ordered by ``last_seen_at DESC``.  Empty when no inbound
        edges target this table.
    """
    try:
        from sqlalchemy import func as _func
        from sqlalchemy import select as _select

        from pointlessql.models import LineageColumnMap

        with session_factory() as session:
            stmt = (
                _select(
                    LineageColumnMap.producer,
                    LineageColumnMap.source_table,
                    _func.max(LineageColumnMap.created_at).label("last_seen_at"),
                )
                .where(
                    LineageColumnMap.target_table == full_name,
                    LineageColumnMap.producer.is_not(None),
                )
                .group_by(LineageColumnMap.producer, LineageColumnMap.source_table)
            )
            grouped: dict[str, dict[str, Any]] = {}
            for row in session.execute(stmt).all():
                producer = str(row[0])
                source = str(row[1]) if row[1] is not None else ""
                seen = row[2]
                slot = grouped.setdefault(
                    producer,
                    {"producer": producer, "source_tables": [], "last_seen_at": seen},
                )
                if source and source not in slot["source_tables"]:
                    slot["source_tables"].append(source)
                if seen is not None and (
                    slot["last_seen_at"] is None or seen > slot["last_seen_at"]
                ):
                    slot["last_seen_at"] = seen
            out = list(grouped.values())
            out.sort(
                key=lambda r: (r["last_seen_at"] is None, r["last_seen_at"]),
                reverse=True,
            )
            return out
    except Exception:  # noqa: BLE001 — best-effort populate
        # bare-broad-ok: external-producers panel renders empty on DB hiccup
        return []


def _cdf_subscription_for_table(
    full_name: str, *, workspace_id: int, session_factory: Any
) -> dict[str, Any] | None:
    """Return the CDF tail subscription for *full_name* if any.

    Workspace-scoped lookup: only returns the subscription that
    belongs to the rendering user's current workspace.

    Args:
        full_name: Three-part UC name of the table.
        workspace_id: Resolved workspace id from the request.
        session_factory: SQLAlchemy session factory bound to the
            metadata DB.

    Returns:
        Serialised subscription dict or ``None`` when no
        subscription exists.  Best-effort: returns ``None`` on any
        DB hiccup so the page still renders.
    """
    try:
        from sqlalchemy import select as _select

        from pointlessql.models import CdfTailSubscription

        with session_factory() as session:
            row = session.scalars(
                _select(CdfTailSubscription).where(
                    CdfTailSubscription.workspace_id == workspace_id,
                    CdfTailSubscription.table_full_name == full_name,
                )
            ).first()
            if row is None:
                return None
            return {
                "id": row.id,
                "table_full_name": row.table_full_name,
                "row_id_column": row.row_id_column,
                "producer_label": row.producer_label,
                "is_active": bool(row.is_active),
                "last_version_processed": row.last_version_processed,
                "last_tailed_at": row.last_tailed_at.isoformat() if row.last_tailed_at else None,
                "last_error": row.last_error,
            }
    except Exception:  # noqa: BLE001 — best-effort populate
        # bare-broad-ok: CDF subscription card renders absent on DB hiccup
        return None


def _cdf_recent_events_for_table(
    full_name: str, *, workspace_id: int, session_factory: Any, limit: int = 50
) -> list[dict[str, Any]]:
    """Return up to *limit* most-recent captured CDF events for *full_name*.

    Args:
        full_name: Three-part UC name of the table.
        workspace_id: Resolved workspace id from the request.
        session_factory: SQLAlchemy session factory.
        limit: Hard cap on returned rows (newest first).

    Returns:
        List of serialised event dicts ordered by ``created_at DESC``.
        Empty list on any DB hiccup or when no events exist yet.
    """
    try:
        from sqlalchemy import select as _select

        from pointlessql.models import CdfTailEvent

        with session_factory() as session:
            rows = list(
                session.scalars(
                    _select(CdfTailEvent)
                    .where(
                        CdfTailEvent.workspace_id == workspace_id,
                        CdfTailEvent.table_full_name == full_name,
                    )
                    .order_by(CdfTailEvent.created_at.desc())
                    .limit(limit)
                ).all()
            )
            return [
                {
                    "id": r.id,
                    "delta_version": r.delta_version,
                    "row_id": r.row_id,
                    "change_type": r.change_type,
                    "commit_timestamp": r.commit_timestamp.isoformat()
                    if r.commit_timestamp
                    else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001 — best-effort populate
        # bare-broad-ok: CDF events tab renders empty on DB hiccup
        return []
