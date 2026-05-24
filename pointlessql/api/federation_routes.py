"""UC federation routes — connections + external locations + credentials.

Owns the three CRUD groups that back Lakehouse Federation
administration plus the six HTML pages (one list + one detail
page per resource family).

* Connections (5 routes + 2 pages)
* External locations (5 routes + 2 pages)
* Credentials (5 routes + 2 pages)

All routes share the same shape: ``require_admin(request)`` first,
then a single soyuz call.  Mutating JSON routes (POST / PATCH /
DELETE) call :func:`audit` once on success so federation changes
leave a tamper-evident trail; read-only routes (GET) skip the
audit helper because there is nothing to record.  HTML pages
catch :class:`CatalogUnavailableError` and render a banner instead
of returning a 5xx so a soyuz outage does not take the admin UI
down.

The admin gate mirrors the soyuz-catalog-side rule that federation
administration is admin-only until a finer-grained CREATE_*
privilege ships.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import admin_uc, render_page_with_fallback
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["federation"])


# -- JSON: Connections --


@router.get("/api/connections")
async def api_list_connections(
    client: UnityCatalogClient = Depends(admin_uc),
) -> list[dict[str, object]]:
    """Return all connections (admin-only)."""
    return await client.list_connections()


@router.post("/api/connections")
async def api_create_connection(
    request: Request,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Create a new connection (admin-only).

    Records the create in ``audit_log`` via :func:`audit` after
    the soyuz call succeeds; a soyuz-side failure raises before
    the audit emit so the trail never claims a creation that did
    not happen.
    """
    result = await client.create_connection(body)
    await audit(request, "create_connection", f"connection:{body.get('name', '?')}")
    return result


@router.get("/api/connections/{name}")
async def api_get_connection(
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Return a single connection (admin-only)."""
    return await client.get_connection(name)


@router.patch("/api/connections/{name}")
async def api_update_connection(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Update a connection (admin-only).

    The patched body is captured verbatim in the ``audit_log``
    detail column (post-success) so a reviewer can see exactly
    what fields the admin changed without having to diff before /
    after.
    """
    result = await client.update_connection(name, body)
    await audit(request, "update_connection", f"connection:{name}", json.dumps(body))
    return result


@router.delete("/api/connections/{name}")
async def api_delete_connection(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, str]:
    """Delete a connection (admin-only).

    Soyuz performs the delete first; only on success is the
    ``audit_log`` row written so the trail never claims a deletion
    that the catalog refused.
    """
    await client.delete_connection(name)
    await audit(request, "delete_connection", f"connection:{name}")
    return {"status": "deleted"}


# -- JSON: External Locations --


@router.get("/api/external-locations")
async def api_list_external_locations(
    client: UnityCatalogClient = Depends(admin_uc),
) -> list[dict[str, object]]:
    """Return all external locations (admin-only)."""
    return await client.list_external_locations()


@router.post("/api/external-locations")
async def api_create_external_location(
    request: Request,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Create a new external location (admin-only).

    Records the create in ``audit_log`` after the soyuz call
    succeeds so a federation change never lands in the catalog
    without leaving an audit trace.
    """
    result = await client.create_external_location(body)
    await audit(request, "create_ext_location", f"ext_location:{body.get('name', '?')}")
    return result


@router.get("/api/external-locations/{name}")
async def api_get_external_location(
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Return a single external location (admin-only)."""
    return await client.get_external_location(name)


@router.patch("/api/external-locations/{name}")
async def api_update_external_location(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Update an external location (admin-only).

    The patched body is recorded verbatim in the ``audit_log``
    detail so a reviewer can see exactly which storage attributes
    or credentials the admin rewired.
    """
    result = await client.update_external_location(name, body)
    await audit(request, "update_ext_location", f"ext_location:{name}", json.dumps(body))
    return result


@router.delete("/api/external-locations/{name}")
async def api_delete_external_location(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, str]:
    """Delete an external location (admin-only).

    Soyuz performs the delete first; the ``audit_log`` row is
    written only on success so the trail stays consistent with
    the catalog state.
    """
    await client.delete_external_location(name)
    await audit(request, "delete_ext_location", f"ext_location:{name}")
    return {"status": "deleted"}


# -- JSON: Credentials --


@router.get("/api/credentials")
async def api_list_credentials(
    client: UnityCatalogClient = Depends(admin_uc),
) -> list[dict[str, object]]:
    """Return all credentials (admin-only)."""
    return await client.list_credentials()


@router.post("/api/credentials")
async def api_create_credential(
    request: Request,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Create a new credential (admin-only).

    Records the create in ``audit_log`` post-success.  The body
    captured by :func:`audit` is the request's ``name``-only
    summary, not the credential secret — the secret never lands
    in the audit trail.
    """
    result = await client.create_credential(body)
    await audit(request, "create_credential", f"credential:{body.get('name', '?')}")
    return result


@router.get("/api/credentials/{name}")
async def api_get_credential(
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Return a single credential (admin-only)."""
    return await client.get_credential(name)


@router.patch("/api/credentials/{name}")
async def api_update_credential(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, object]:
    """Update a credential (admin-only).

    The patched body is recorded in the ``audit_log`` detail
    column after soyuz accepts the patch.  Callers passing a new
    secret should rely on soyuz-side redaction at read time —
    this route stores what the request body sent.
    """
    result = await client.update_credential(name, body)
    await audit(request, "update_credential", f"credential:{name}", json.dumps(body))
    return result


@router.delete("/api/credentials/{name}")
async def api_delete_credential(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> dict[str, str]:
    """Delete a credential (admin-only).

    Soyuz performs the delete first; only on success is the
    ``audit_log`` row written so the trail never claims a deletion
    that the catalog refused.
    """
    await client.delete_credential(name)
    await audit(request, "delete_credential", f"credential:{name}")
    return {"status": "deleted"}


# -- HTML pages --


@router.get("/connections", response_class=HTMLResponse)
async def connections_index(
    request: Request,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """List all connections (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/connections.html",
        client.list_connections,
        context_key="connections",
        extra_context={"active_page": "connections", "list_page": True},
    )


@router.get("/connections/{name}", response_class=HTMLResponse)
async def connection_detail(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """Show a single connection (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/connection.html",
        lambda: client.get_connection(name),
        context_key="connection",
        extra_context={"name": name, "active_page": "connections"},
    )


@router.get("/external-locations", response_class=HTMLResponse)
async def external_locations_index(
    request: Request,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """List all external locations (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/external_locations.html",
        client.list_external_locations,
        context_key="locations",
        extra_context={"active_page": "external_locations", "list_page": True},
    )


@router.get("/external-locations/{name}", response_class=HTMLResponse)
async def external_location_detail(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """Show a single external location (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/external_location.html",
        lambda: client.get_external_location(name),
        context_key="location",
        extra_context={"name": name, "active_page": "external_locations"},
    )


@router.get("/credentials", response_class=HTMLResponse)
async def credentials_index(
    request: Request,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """List all credentials (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/credentials.html",
        client.list_credentials,
        context_key="credentials",
        extra_context={"active_page": "credentials", "list_page": True},
    )


@router.get("/credentials/{name}", response_class=HTMLResponse)
async def credential_detail(
    request: Request,
    name: str,
    client: UnityCatalogClient = Depends(admin_uc),
) -> HTMLResponse:
    """Show a single credential (admin-only)."""
    return await render_page_with_fallback(
        request,
        "pages/credential.html",
        lambda: client.get_credential(name),
        context_key="credential",
        extra_context={"name": name, "active_page": "credentials"},
    )
