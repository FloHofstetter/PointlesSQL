"""Catalog + schema mutation endpoints.

* ``POST /api/catalogs`` — admin-only create.
* ``POST /api/catalogs/{cat}/sync`` — admin-only refresh.
* ``PATCH /api/catalogs/{cat}`` — MODIFY on the target.
* ``PATCH /api/catalogs/{cat}/schemas/{sch}`` — MODIFY on the target.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services.authorization import MODIFY, check_privilege

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


@router.post("/api/catalogs")
async def api_create_catalog(
    request: Request,
    body: dict[str, Any] = Body(...),
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
    sync worker. Returns the :class:`SyncRun` snapshot so the UI can
    render the new history card entry immediately.
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
    options_raw: Any = connection.get("options") or {}
    options = cast(dict[str, Any], options_raw) if isinstance(options_raw, dict) else {}
    credential_name = options.get("credential_name")
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
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
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
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "schema",
        full_name,
        MODIFY,
    )
    result = await client.update_schema(catalog_name, schema_name, patch)
    await audit(request, "update_schema", f"schema:{full_name}", json.dumps(patch))
    return result

