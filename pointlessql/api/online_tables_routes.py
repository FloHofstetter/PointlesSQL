"""Online-tables routes — synced-table lifecycle + the lookup API.

JSON surface under ``/api/online-tables`` plus the ``/online-tables``
HTML page.  Creating and syncing require an authenticated user;
deleting additionally requires admin or creator.  The lookup endpoint
is the low-latency read path over the synced target — primary-key
columns only, value always bound as a parameter.

Integration note: this router is exported but **not registered** —
the integrating session includes it from the bootstrap router list
(``app.include_router(online_tables_routes.router)``).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_templates, get_user
from pointlessql.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.synced_tables import SyncedTable
from pointlessql.services import synced_tables as synced_tables_service
from pointlessql.services._executor import run_sync

router = APIRouter(tags=["online-tables"])


def _serialize(row: SyncedTable) -> dict[str, Any]:
    """Project a synced-table row to a JSON-safe dict."""
    return {
        "id": row.id,
        "name": row.name,
        "source_fqn": row.source_fqn,
        "target_url": row.target_url,
        "target_table": row.target_table,
        "primary_keys": synced_tables_service.parse_primary_keys(row.primary_keys),
        "mode": row.mode,
        "last_synced_version": row.last_synced_version,
        "status": row.status,
        "last_error": row.last_error,
        "rows_synced": row.rows_synced,
        "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _ensure_synced_table(request: Request, name: str) -> SyncedTable:
    """Return the active workspace's synced table or raise a 404.

    Args:
        request: Incoming FastAPI request.
        name: Synced-table name from the URL.

    Returns:
        The detached synced-table row.

    Raises:
        ResourceNotFoundError: When no synced table with *name*
            exists in the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = synced_tables_service.get_synced_table(factory, workspace_id=workspace_id, name=name)
    if row is None:
        raise ResourceNotFoundError(f"Synced table '{name}' not found.")
    return row


async def _resolve_storage(request: Request, source_fqn: str) -> str:
    """Resolve a three-part UC name to its Delta storage location.

    Args:
        request: Incoming FastAPI request (for the UC client).
        source_fqn: Three-part UC table name.

    Returns:
        The storage location URI.

    Raises:
        ValidationError: When *source_fqn* is not three-part.
        ResourceNotFoundError: When the table has no
            ``storage_location`` registered.
    """
    parts = source_fqn.split(".")
    if len(parts) != 3:
        raise ValidationError(
            f"source_fqn must be three parts 'catalog.schema.table', got {source_fqn!r}"
        )
    table_info = cast(
        "dict[str, Any]",
        await request.app.state.uc_client.get_table(parts[0], parts[1], parts[2]),
    )
    storage = table_info.get("storage_location") if table_info else None
    if not storage or not isinstance(storage, str):
        raise ResourceNotFoundError(f"Table {source_fqn!r} has no storage_location.")
    return storage


@router.get("/api/online-tables")
async def api_list_online_tables(request: Request) -> dict[str, Any]:
    """List the active workspace's synced tables."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = await run_sync(
        synced_tables_service.list_synced_tables, factory, workspace_id=workspace_id
    )
    return {"online_tables": [_serialize(row) for row in rows]}


@router.post("/api/online-tables")
async def api_create_online_table(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a synced table in ``idle`` state.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name", "source_fqn", "target_url", "target_table",
            "primary_keys"?, "mode"?}`` — ``primary_keys`` is a
            comma-separated column list, required for ``cdf`` mode.

    Returns:
        The serialized synced-table row.

    Raises:
        ValidationError: On malformed input or a duplicate name.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to create online tables")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    raw_keys = body.get("primary_keys")
    try:
        row = await run_sync(
            synced_tables_service.create_synced_table,
            factory,
            workspace_id=workspace_id,
            name=str(body.get("name", "")),
            source_fqn=str(body.get("source_fqn", "")),
            target_url=str(body.get("target_url", "")),
            target_table=str(body.get("target_table", "")),
            primary_keys=str(raw_keys) if raw_keys else None,
            mode=str(body.get("mode", "full")),
            principal=user["email"],
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "synced_table.created",
        f"synced_table:{row.name}",
        {"source_fqn": row.source_fqn, "mode": row.mode},
    )
    return _serialize(row)


@router.delete("/api/online-tables/{name}")
async def api_delete_online_table(request: Request, name: str) -> dict[str, Any]:
    """Delete a synced table (admin or creator only).

    The target table itself is left in place — deleting the row only
    stops PointlesSQL from syncing it.

    Args:
        request: Incoming FastAPI request.
        name: Synced-table name.

    Returns:
        ``{"deleted": bool}``.

    Raises:
        PermissionDeniedError: When the caller is neither an admin
            nor the creator of the synced table.
    """
    user = get_user(request)
    row = _ensure_synced_table(request, name)
    if user["id"] <= 0 or (not user["is_admin"] and row.created_by != user["email"]):
        raise PermissionDeniedError("only an admin or the creator may delete a synced table")
    factory = request.app.state.session_factory
    deleted = await run_sync(
        synced_tables_service.delete_synced_table, factory, synced_table_id=row.id
    )
    if deleted:
        await audit(
            request,
            "synced_table.deleted",
            f"synced_table:{row.name}",
            {"id": row.id},
        )
    return {"deleted": deleted}


@router.post("/api/online-tables/{name}/sync")
async def api_sync_online_table(request: Request, name: str) -> dict[str, Any]:
    """Run one sync of the synced table's Delta source into its target.

    Args:
        request: Incoming FastAPI request.
        name: Synced-table name.

    Returns:
        ``{"rows_affected", "version", "table"}`` — the per-run stats
        plus the refreshed serialized row.

    Raises:
        ValidationError: When the sync fails (the row is left in
            ``failed`` state with the error recorded).
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to sync online tables")
    row = _ensure_synced_table(request, name)
    storage = await _resolve_storage(request, row.source_fqn)
    factory = request.app.state.session_factory
    try:
        result = await run_sync(
            synced_tables_service.sync_once,
            factory,
            synced_table_id=row.id,
            storage_location=storage,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "synced_table.synced",
        f"synced_table:{row.name}",
        {"rows": result["rows_affected"], "version": result["version"]},
    )
    return {
        "rows_affected": result["rows_affected"],
        "version": result["version"],
        "table": _serialize(_ensure_synced_table(request, name)),
    }


@router.get("/api/online-tables/{name}/lookup")
async def api_lookup_online_table(
    request: Request,
    name: str,
    key_column: str,
    key: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Point-read rows from the synced target by primary key.

    Args:
        request: Incoming FastAPI request.
        name: Synced-table name.
        key_column: Column to filter on; must be one of the synced
            table's primary keys.
        key: Value to match (always parameter-bound).
        limit: Maximum rows returned.

    Returns:
        ``{"rows": [...], "row_count": int}``.

    Raises:
        ValidationError: When *key_column* is not a primary-key
            column or the target cannot be queried.
    """
    row = _ensure_synced_table(request, name)
    factory = request.app.state.session_factory
    try:
        rows = await run_sync(
            synced_tables_service.lookup,
            factory,
            synced_table_id=row.id,
            key_column=key_column,
            key_value=key,
            limit=limit,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return {"rows": rows, "row_count": len(rows)}


@router.get("/online-tables", response_class=HTMLResponse)
async def online_tables_page(request: Request):
    """Render the online-tables browser (list + create + lookup tester)."""
    return get_templates(request).TemplateResponse(
        request,
        "pages/online_tables.html",
        {"active_page": "online-tables"},
    )
