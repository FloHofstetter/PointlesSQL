"""Governance routes — table stats, tags, permissions, lineage, catalog mutations.

Sprint 87c split out of ``api/main.py``.  Owns the cluster of
endpoints that govern UC metadata + access control:

* Table column statistics (``/api/tables/.../profile`` POST,
  ``/api/tables/.../stats`` GET/DELETE — Sprint 56).
* Notebook scratch-from-table helper
  (``POST .../tables/.../open-in-notebook``).
* Catalog mutations (``POST /api/catalogs``, ``POST .../sync``,
  ``PATCH /api/catalogs/{cat}``, ``PATCH …/schemas/{schema}``).
* Tags + permissions (``/api/tags`` + ``/api/permissions`` +
  ``/api/effective-permissions`` GET/PATCH).
* Lineage (``GET /api/lineage/{full_name}``).

Authorization model is unchanged from the pre-split shape:

* Profile + stats GET require SELECT (admin short-circuits).
* Stats DELETE + open-in-notebook + create-catalog + sync-catalog
  are admin-only.
* Catalog/schema PATCH need MODIFY on the target.
* Tag PATCH needs MODIFY; permission PATCH needs MANAGE_GRANTS.
* Lineage GET needs SELECT on the table.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_uc_client, get_user, require_admin
from pointlessql.exceptions import AuthorizationError, ValidationError
from pointlessql.services import notebook_doc as notebook_doc_service
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    MODIFY,
    SELECT,
    check_privilege,
)
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


def split_full_name(full_name: str) -> tuple[str, str, str]:
    """Split a UC three-part name, raising on bad shape.

    Args:
        full_name: Dotted identifier ``catalog.schema.table``.

    Returns:
        Tuple ``(catalog, schema, table)``.

    Raises:
        ValidationError: If *full_name* does not have exactly three
            non-empty dotted parts.
    """
    parts = full_name.split(".")
    if len(parts) != 3 or not all(p for p in parts):
        raise ValidationError(
            f"Expected three-part catalog.schema.table, got {full_name!r}.",
        )
    return parts[0], parts[1], parts[2]


async def enforce_table_profile_access(
    request: Request, full_name: str,
) -> dict[str, Any]:
    """Resolve table info and check that the caller may profile it.

    Admin short-circuits SELECT enforcement; every other caller must
    hold SELECT on the table before they can trigger a profile run.

    Args:
        request: Incoming request.
        full_name: Three-part UC name.

    Returns:
        The UC ``table_info`` dict.

    Raises:
        CatalogNotFoundError: When the table is missing or has no
            ``storage_location``.
        AuthorizationError: When the caller lacks SELECT on the table.
    """  # noqa: DOC502,DOC503 — raised via await below
    from pointlessql.exceptions import CatalogNotFoundError

    client = get_uc_client(request)
    user = get_user(request)
    email = user.get("email", "")
    is_admin = bool(user.get("is_admin", False))
    catalog, schema, table = split_full_name(full_name)
    table_info = await client.get_table(catalog, schema, table)
    if not table_info:
        raise CatalogNotFoundError(f"Table {full_name!r} not found.")
    storage_location = table_info.get("storage_location")
    if not isinstance(storage_location, str) or not storage_location:
        raise CatalogNotFoundError(
            f"Table {full_name!r} has no storage_location on soyuz-catalog.",
        )
    await check_privilege(client, email, is_admin, "table", full_name, SELECT)
    return table_info


@router.post("/api/tables/{full_name:path}/profile")
async def api_profile_table(
    request: Request, full_name: str,
) -> dict[str, Any]:
    """Compute + cache per-column statistics for the Delta table.

    The caller must hold SELECT on the table or be an administrator.
    Results are cached by ``(full_name, delta_log_version)`` so a
    second call at the same Delta version is a single index seek.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name (path-encoded).

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and a
        ``columns`` list of serialised stats rows.

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    table_info = await enforce_table_profile_access(request, full_name)
    storage_location = str(table_info.get("storage_location") or "")
    columns = [
        {"name": str(c.get("name") or ""), "type": str(c.get("type_text") or "")}
        for c in (table_info.get("columns") or [])
        if c.get("name")
    ]
    factory = getattr(request.app.state, "session_factory", None)

    # Short-circuit: if the current version is already cached we
    # still surface it but do not recompute.
    current_version = await asyncio.to_thread(
        ts_service.read_delta_log_version, storage_location,
    )
    if factory is not None:
        cached = await asyncio.to_thread(
            ts_service.read_cached,
            factory, full_name=full_name, delta_log_version=current_version,
        )
        if cached is not None:
            await audit(
                request, "table.profile_cache_hit",
                f"table:{full_name}",
                {"delta_log_version": current_version},
            )
            return {
                "full_name": full_name,
                "delta_log_version": current_version,
                "cached": True,
                "columns": cached,
            }

    stats = await asyncio.to_thread(
        ts_service.compute_stats, full_name, storage_location, columns,
    )
    if factory is not None:
        await asyncio.to_thread(
            ts_service.write_cached,
            factory, full_name=full_name,
            delta_log_version=current_version, stats=stats,
        )
    await audit(
        request, "table.profiled", f"table:{full_name}",
        {
            "delta_log_version": current_version,
            "column_count": len(stats),
        },
    )
    serialised = [
        {
            "column_name": col_name,
            "delta_log_version": current_version,
            "computed_at": datetime.now(UTC).isoformat(),
            "stats": stats_dict,
        }
        for col_name, stats_dict in stats.items()
    ]
    return {
        "full_name": full_name,
        "delta_log_version": current_version,
        "cached": False,
        "columns": serialised,
    }


@router.get("/api/tables/{full_name:path}/stats")
async def api_get_table_stats(
    request: Request, full_name: str, version: int | None = None,
) -> dict[str, Any]:
    """Return cached stats for a UC table, optionally pinned to a version.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name.
        version: Optional Delta log version; defaults to the latest
            cached version for this table.

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and
        ``columns`` (empty list if nothing is cached yet).

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    await enforce_table_profile_access(request, full_name)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"full_name": full_name, "delta_log_version": None, "columns": []}
    cached = await asyncio.to_thread(
        ts_service.read_cached,
        factory, full_name=full_name, delta_log_version=version,
    )
    if cached is None:
        return {"full_name": full_name, "delta_log_version": version, "columns": []}
    latest_version = max(row["delta_log_version"] for row in cached)
    return {
        "full_name": full_name,
        "delta_log_version": version if version is not None else latest_version,
        "columns": cached,
    }


@router.delete(
    "/api/tables/{full_name:path}/stats", status_code=204,
)
async def api_delete_table_stats(
    request: Request, full_name: str,
) -> Response:
    """Evict every cached statistics row for *full_name* (admin only).

    Args:
        request: Incoming request.
        full_name: UC three-part name.

    Returns:
        Empty 204.
    """
    from pointlessql.services import table_stats as ts_service

    require_admin(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=204)
    removed = await asyncio.to_thread(
        ts_service.delete_cached, factory, full_name,
    )
    await audit(
        request, "table.stats_cleared", f"table:{full_name}",
        {"rows_removed": removed},
    )
    return Response(status_code=204)


@router.post(
    "/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/open-in-notebook",
)
async def api_open_in_notebook(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> dict[str, Any]:
    """Create a scratch ``.py`` notebook pre-filled with ``pql.table(...)``.

    Admin-only to keep the workspace clean. Sprint 63 writes a
    jupytext Percent-format ``.py`` under
    ``{notebooks_dir}/scratch/`` (one markdown cell + one code cell
    with UUID markers so the native editor picks it up on mount).
    Returns the on-disk path plus a ``/notebook/editor`` URL the
    client navigates to with ``window.location.assign``.
    """
    import secrets
    import uuid

    require_admin(request)
    settings: Settings = request.app.state.settings
    full_name = f"{catalog_name}.{schema_name}.{table_name}"

    sanitiser = re.compile(r"[^A-Za-z0-9_-]")
    stem = "_".join(sanitiser.sub("_", part) for part in (catalog_name, schema_name, table_name))
    filename = f"{stem}_{secrets.token_hex(3)}.py"
    scratch_dir = settings.jupyter.notebooks_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    target = notebook_doc_service.resolve_py_notebook_path(
        settings.jupyter.notebooks_dir.resolve(),
        f"scratch/{filename}",
        must_exist=False,
    )

    cells = [
        notebook_doc_service.NotebookCell(
            id=str(uuid.uuid4()),
            cell_type="markdown",
            source=(
                f"# Scratch: `{full_name}`\n\n"
                "Generated from the PointlesSQL table detail page."
            ),
        ),
        notebook_doc_service.NotebookCell(
            id=str(uuid.uuid4()),
            cell_type="code",
            source=(
                "from pointlessql import PQL\n\n"
                "pql = PQL()\n"
                f'df = pql.table("{full_name}")\n'
                "df.head()"
            ),
        ),
    ]
    notebook_doc_service.save_document(target, cells)

    await audit(request, "open_in_notebook", f"table:{full_name}", f"scratch/{filename}")
    relative = f"scratch/{filename}"
    editor_url = f"/notebook/editor?path={relative}"
    return {"path": relative, "editor_url": editor_url}


@router.post("/api/catalogs")
async def api_create_catalog(
    request: Request, body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Create a new catalog.

    Admin-only so foreign-catalog creation (which binds a Connection)
    stays aligned with the federation admin-only rule. Once soyuz-catalog
    exposes a finer-grained CREATE_CATALOG privilege we can switch to
    ``check_privilege`` on the metastore like the other writes.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.create_catalog(body)
    await audit(request, "create_catalog", f"catalog:{body.get('name', '?')}", json.dumps(body))
    return result


@router.post("/api/catalogs/{catalog_name}/sync")
async def api_sync_catalog(request: Request, catalog_name: str) -> dict[str, object]:
    """Trigger a Postgres → UC sync for a foreign catalog (admin-only).

    Reads the catalog's bound Connection, resolves a Credential by the
    optional ``credential_name`` key in its options, and runs the
    Sprint 18 sync worker. Returns the :class:`SyncRun` snapshot so
    the UI can render the new history card entry immediately.
    """
    require_admin(request)
    client = get_uc_client(request)
    catalog = await client.get_catalog(catalog_name)
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise AuthorizationError(
            principal=get_user(request).get("email", ""),
            privilege="sync",
            securable_type="catalog",
            full_name=catalog_name,
        )
    connection = await client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = options.get("credential_name") if isinstance(options, dict) else None
    if credential_name:
        credential = await client.get_credential(str(credential_name))
    factory = request.app.state.session_factory
    run = await pg_sync_service.run_sync(
        uc=client,
        factory=factory,
        catalog_name=catalog_name,
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )
    await audit(request, "sync_catalog", f"catalog:{catalog_name}")
    return {
        "id": run.id,
        "catalog_name": run.catalog_name,
        "status": run.status,
        "added_count": run.added_count,
        "changed_count": run.changed_count,
        "dropped_count": run.dropped_count,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
    }


@router.patch("/api/catalogs/{catalog_name}")
async def api_update_catalog(
    request: Request,
    catalog_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a catalog."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        MODIFY,
    )
    result = await client.update_catalog(catalog_name, patch)
    await audit(request, "update_catalog", f"catalog:{catalog_name}", json.dumps(patch))
    return result


@router.patch("/api/catalogs/{catalog_name}/schemas/{schema_name}")
async def api_update_schema(
    request: Request,
    catalog_name: str,
    schema_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a schema."""
    client = get_uc_client(request)
    user = get_user(request)
    full_name = f"{catalog_name}.{schema_name}"
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "schema",
        full_name,
        MODIFY,
    )
    result = await client.update_schema(catalog_name, schema_name, patch)
    await audit(request, "update_schema", f"schema:{full_name}", json.dumps(patch))
    return result


@router.get("/api/tags/{securable_type}/{full_name:path}")
async def api_get_tags(
    request: Request, securable_type: str, full_name: str,
) -> list[dict[str, object]]:
    """Return tags for a securable."""
    client = get_uc_client(request)
    return await client.get_tags(securable_type, full_name)


@router.patch("/api/tags/{securable_type}/{full_name:path}")
async def api_update_tags(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update tags for a securable. Body: {"changes": [...]}."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MODIFY,
    )
    result = await client.update_tags(securable_type, full_name, body.get("changes", []))
    await audit(
        request,
        "update_tags",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@router.get("/api/permissions/{securable_type}/{full_name:path}")
async def api_get_permissions(
    request: Request, securable_type: str, full_name: str,
) -> list[dict[str, object]]:
    """Return privilege assignments for a securable."""
    client = get_uc_client(request)
    return await client.get_permissions(securable_type, full_name)


@router.patch("/api/permissions/{securable_type}/{full_name:path}")
async def api_update_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update permissions for a securable. Body: {"changes": [...]}."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MANAGE_GRANTS,
    )
    result = await client.update_permissions(securable_type, full_name, body.get("changes", []))
    await audit(
        request,
        "update_permissions",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@router.get("/api/effective-permissions/{securable_type}/{full_name:path}")
async def api_get_effective_permissions(
    request: Request, securable_type: str, full_name: str,
) -> list[dict[str, object]]:
    """Return effective (inherited) permissions for a securable."""
    client = get_uc_client(request)
    return await client.get_effective_permissions(securable_type, full_name)


@router.get("/api/lineage/{full_name:path}")
async def api_lineage(request: Request, full_name: str, depth: int = 3) -> dict[str, object]:
    """Return combined upstream/downstream lineage for a table."""
    client = get_uc_client(request)
    user = get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    return await client.get_lineage(full_name, depth)
