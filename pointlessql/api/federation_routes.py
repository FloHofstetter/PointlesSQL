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

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_uc_client, require_admin
from pointlessql.exceptions import CatalogUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["federation"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


# -- JSON: Connections --


@router.get("/api/connections")
async def api_list_connections(request: Request) -> list[dict[str, object]]:
    """Return all connections (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.list_connections()


@router.post("/api/connections")
async def api_create_connection(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Create a new connection (admin-only).

    Records the create in ``audit_log`` via :func:`audit` after
    the soyuz call succeeds; a soyuz-side failure raises before
    the audit emit so the trail never claims a creation that did
    not happen.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.create_connection(body)
    await audit(request, "create_connection", f"connection:{body.get('name', '?')}")
    return result


@router.get("/api/connections/{name}")
async def api_get_connection(request: Request, name: str) -> dict[str, object]:
    """Return a single connection (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.get_connection(name)


@router.patch("/api/connections/{name}")
async def api_update_connection(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Update a connection (admin-only).

    The patched body is captured verbatim in the ``audit_log``
    detail column (post-success) so a reviewer can see exactly
    what fields the admin changed without having to diff before /
    after.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.update_connection(name, body)
    await audit(request, "update_connection", f"connection:{name}", json.dumps(body))
    return result


@router.delete("/api/connections/{name}")
async def api_delete_connection(request: Request, name: str) -> dict[str, str]:
    """Delete a connection (admin-only).

    Soyuz performs the delete first; only on success is the
    ``audit_log`` row written so the trail never claims a deletion
    that the catalog refused.
    """
    require_admin(request)
    client = get_uc_client(request)
    await client.delete_connection(name)
    await audit(request, "delete_connection", f"connection:{name}")
    return {"status": "deleted"}


# -- JSON: External Locations --


@router.get("/api/external-locations")
async def api_list_external_locations(request: Request) -> list[dict[str, object]]:
    """Return all external locations (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.list_external_locations()


@router.post("/api/external-locations")
async def api_create_external_location(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Create a new external location (admin-only).

    Records the create in ``audit_log`` after the soyuz call
    succeeds so a federation change never lands in the catalog
    without leaving an audit trace.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.create_external_location(body)
    await audit(request, "create_ext_location", f"ext_location:{body.get('name', '?')}")
    return result


@router.get("/api/external-locations/{name}")
async def api_get_external_location(request: Request, name: str) -> dict[str, object]:
    """Return a single external location (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.get_external_location(name)


@router.patch("/api/external-locations/{name}")
async def api_update_external_location(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Update an external location (admin-only).

    The patched body is recorded verbatim in the ``audit_log``
    detail so a reviewer can see exactly which storage attributes
    or credentials the admin rewired.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.update_external_location(name, body)
    await audit(request, "update_ext_location", f"ext_location:{name}", json.dumps(body))
    return result


@router.delete("/api/external-locations/{name}")
async def api_delete_external_location(request: Request, name: str) -> dict[str, str]:
    """Delete an external location (admin-only).

    Soyuz performs the delete first; the ``audit_log`` row is
    written only on success so the trail stays consistent with
    the catalog state.
    """
    require_admin(request)
    client = get_uc_client(request)
    await client.delete_external_location(name)
    await audit(request, "delete_ext_location", f"ext_location:{name}")
    return {"status": "deleted"}


# -- JSON: Credentials --


@router.get("/api/credentials")
async def api_list_credentials(request: Request) -> list[dict[str, object]]:
    """Return all credentials (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.list_credentials()


@router.post("/api/credentials")
async def api_create_credential(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Create a new credential (admin-only).

    Records the create in ``audit_log`` post-success.  The body
    captured by :func:`audit` is the request's ``name``-only
    summary, not the credential secret — the secret never lands
    in the audit trail.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.create_credential(body)
    await audit(request, "create_credential", f"credential:{body.get('name', '?')}")
    return result


@router.get("/api/credentials/{name}")
async def api_get_credential(request: Request, name: str) -> dict[str, object]:
    """Return a single credential (admin-only)."""
    require_admin(request)
    client = get_uc_client(request)
    return await client.get_credential(name)


@router.patch("/api/credentials/{name}")
async def api_update_credential(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Update a credential (admin-only).

    The patched body is recorded in the ``audit_log`` detail
    column after soyuz accepts the patch.  Callers passing a new
    secret should rely on soyuz-side redaction at read time —
    this route stores what the request body sent.
    """
    require_admin(request)
    client = get_uc_client(request)
    result = await client.update_credential(name, body)
    await audit(request, "update_credential", f"credential:{name}", json.dumps(body))
    return result


@router.delete("/api/credentials/{name}")
async def api_delete_credential(request: Request, name: str) -> dict[str, str]:
    """Delete a credential (admin-only).

    Soyuz performs the delete first; only on success is the
    ``audit_log`` row written so the trail never claims a deletion
    that the catalog refused.
    """
    require_admin(request)
    client = get_uc_client(request)
    await client.delete_credential(name)
    await audit(request, "delete_credential", f"credential:{name}")
    return {"status": "deleted"}


# -- HTML pages --


@router.get("/connections", response_class=HTMLResponse)
async def connections_index(request: Request) -> HTMLResponse:
    """List all connections (admin-only).

    Renders an empty list with an inline error banner when soyuz is
    unreachable so an outage of the catalog does not surface as a
    5xx; the page still loads and the banner explains why the
    table is empty.
    """
    require_admin(request)
    client = get_uc_client(request)
    connections: list[dict[str, Any]] = []
    error: str | None = None
    try:
        connections = await client.list_connections()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/connections.html",
        {
            "connections": connections,
            "error": error,
            "active_page": "connections",
            "list_page": True,
        },
    )


@router.get("/connections/{name}", response_class=HTMLResponse)
async def connection_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single connection (admin-only).

    A soyuz outage renders an error banner instead of a 5xx so the
    rest of the admin UI keeps working while the catalog recovers.
    """
    require_admin(request)
    client = get_uc_client(request)
    connection: dict[str, Any] | None = None
    error: str | None = None
    try:
        connection = await client.get_connection(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/connection.html",
        {"connection": connection, "name": name, "error": error, "active_page": "connections"},
    )


@router.get("/external-locations", response_class=HTMLResponse)
async def external_locations_index(request: Request) -> HTMLResponse:
    """List all external locations (admin-only).

    Renders an empty list with an inline error banner when soyuz is
    unreachable so an outage does not take the page down — the
    user sees a clear "catalog unavailable" message rather than a
    500.
    """
    require_admin(request)
    client = get_uc_client(request)
    locations: list[dict[str, Any]] = []
    error: str | None = None
    try:
        locations = await client.list_external_locations()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/external_locations.html",
        {
            "locations": locations,
            "error": error,
            "active_page": "external_locations",
            "list_page": True,
        },
    )


@router.get("/external-locations/{name}", response_class=HTMLResponse)
async def external_location_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single external location (admin-only).

    A soyuz outage renders an error banner instead of a 5xx so a
    catalog hiccup does not break the navigation back to the
    external-locations list.
    """
    require_admin(request)
    client = get_uc_client(request)
    location: dict[str, Any] | None = None
    error: str | None = None
    try:
        location = await client.get_external_location(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/external_location.html",
        {"location": location, "name": name, "error": error, "active_page": "external_locations"},
    )


@router.get("/credentials", response_class=HTMLResponse)
async def credentials_index(request: Request) -> HTMLResponse:
    """List all credentials (admin-only).

    Renders an empty list with an inline error banner when soyuz is
    unreachable so the page still loads during a catalog outage —
    the user sees a clear "catalog unavailable" message rather than
    a 500.
    """
    require_admin(request)
    client = get_uc_client(request)
    credentials: list[dict[str, Any]] = []
    error: str | None = None
    try:
        credentials = await client.list_credentials()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/credentials.html",
        {
            "credentials": credentials,
            "error": error,
            "active_page": "credentials",
            "list_page": True,
        },
    )


@router.get("/credentials/{name}", response_class=HTMLResponse)
async def credential_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single credential (admin-only).

    A soyuz outage renders an error banner instead of a 5xx so the
    admin UI stays navigable while the catalog recovers.  The
    page never displays the credential's secret material — soyuz
    redacts it at read time.
    """
    require_admin(request)
    client = get_uc_client(request)
    credential: dict[str, Any] | None = None
    error: str | None = None
    try:
        credential = await client.get_credential(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _templates(request).TemplateResponse(
        request,
        "pages/credential.html",
        {"credential": credential, "name": name, "error": error, "active_page": "credentials"},
    )
