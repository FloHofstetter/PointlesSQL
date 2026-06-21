"""Admin surface for the governed MCP service registry.

PointlesSQL already exposes its own Lens tools *as* an MCP server; this
surface is the governed counterpart — a Unity-Catalog-shaped inventory
of approved *external* MCP services (Slack, Jira, GitHub, a partner's
own endpoint, …).  Admins register a service, curate its advertised
tools with a per-tool allow toggle, and enable/disable the whole
service; developers read the published surface (enabled services + their
enabled tools) through the discovery endpoint.

The registration is governance metadata in PointlesSQL's own DB, not a
live connection — invoking a service's tools is the eventual
enforcement path, kept out of this CRUD-and-discovery surface.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.services import mcp_registry

router = APIRouter(tags=["admin-mcp-services"])


@router.get("/admin/mcp-services", response_class=HTMLResponse)
async def admin_mcp_services_index(request: Request) -> HTMLResponse:
    """Render the MCP service registry console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_mcp_services.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_mcp_services.html",
        {
            "active_page": "admin",
            "transports": list(mcp_registry.MCP_SERVICE_TRANSPORTS),
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/mcp-services")
async def list_mcp_services(request: Request) -> dict[str, Any]:
    """List every registered MCP service in the workspace, tools included.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"services": [...]}`` — admin view spanning enabled and
        disabled services.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {"services": mcp_registry.list_services(factory, workspace_id=workspace_id)}


@router.get("/api/admin/mcp-services/discover")
async def discover_mcp_services(request: Request) -> dict[str, Any]:
    """Return the published surface — enabled services + enabled tools.

    The developer-facing discovery view; disabled services and disabled
    tools are filtered out entirely.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"services": [...]}`` carrying only the published surface.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {"services": mcp_registry.discover_services(factory, workspace_id=workspace_id)}


@router.post("/api/admin/mcp-services")
async def register_mcp_service(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Register a new external MCP service.

    Args:
        request: Incoming FastAPI request.
        body: JSON with ``name``, ``url``, ``transport`` and optional
            ``description`` / ``secret_scope``.

    Returns:
        ``{"service": {...}}`` with the created service.  A malformed
        field or a taken name propagates the service layer's
        :class:`ValueError`, mapped to HTTP 400 by the global handler.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    created_by = get_user(request)["email"] or None
    service = mcp_registry.register_service(
        factory,
        workspace_id=workspace_id,
        name=body.get("name"),
        url=body.get("url"),
        transport=body.get("transport"),
        description=body.get("description"),
        secret_scope=body.get("secret_scope"),
        created_by=created_by,
    )
    return {"service": service}


@router.patch("/api/admin/mcp-services/{service_id}")
async def update_mcp_service(
    request: Request,
    service_id: int,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Patch a service's fields and/or its enabled state.

    Args:
        request: Incoming FastAPI request.
        service_id: Primary key of the service to patch.
        body: JSON with any of ``name`` / ``url`` / ``transport`` /
            ``description`` / ``secret_scope`` to update fields, and/or
            ``enabled`` (bool) to publish or un-publish.

    Returns:
        ``{"service": {...}}`` with the updated service.

    Raises:
        ValueError: When the service is unknown or a field is malformed
            (mapped to HTTP 400 by the global handler).
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    has_field = any(
        key in body for key in ("name", "url", "transport", "description", "secret_scope")
    )
    if has_field:
        mcp_registry.update_service(
            factory,
            service_id=service_id,
            workspace_id=workspace_id,
            name=body.get("name"),
            url=body.get("url"),
            transport=body.get("transport"),
            description=body.get("description"),
            secret_scope=body.get("secret_scope"),
        )
    if "enabled" in body:
        mcp_registry.set_service_enabled(
            factory,
            service_id=service_id,
            workspace_id=workspace_id,
            enabled=bool(body.get("enabled")),
        )
    service = mcp_registry.get_service(factory, service_id=service_id, workspace_id=workspace_id)
    if service is None:
        raise ValueError(f"MCP service {service_id} not found")
    return {"service": service}


@router.delete("/api/admin/mcp-services/{service_id}")
async def delete_mcp_service(request: Request, service_id: int) -> dict[str, Any]:
    """Delete a service and all of its tools.

    Args:
        request: Incoming FastAPI request.
        service_id: Primary key of the service.

    Returns:
        ``{"deleted": <bool>}``.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "deleted": mcp_registry.delete_service(
            factory, service_id=service_id, workspace_id=workspace_id
        )
    }


@router.post("/api/admin/mcp-services/{service_id}/tools")
async def add_mcp_tool(
    request: Request,
    service_id: int,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Add one advertised tool to a service's inventory.

    Args:
        request: Incoming FastAPI request.
        service_id: Primary key of the owning service.
        body: JSON with ``name`` and optional ``description``.

    Returns:
        ``{"tool": {...}}`` with the created tool.  An unknown service
        or a malformed / taken tool name propagates the service layer's
        :class:`ValueError`, mapped to HTTP 400 by the global handler.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    tool = mcp_registry.add_tool(
        factory,
        service_id=service_id,
        workspace_id=workspace_id,
        name=body.get("name"),
        description=body.get("description"),
    )
    return {"tool": tool}


@router.patch("/api/admin/mcp-services/{service_id}/tools/{tool_id}")
async def update_mcp_tool(
    request: Request,
    service_id: int,
    tool_id: int,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Toggle a tool's per-tool allow flag.

    Args:
        request: Incoming FastAPI request.
        service_id: Primary key of the owning service.
        tool_id: Primary key of the tool.
        body: JSON with ``enabled`` (bool).

    Returns:
        ``{"tool": {...}}`` with the updated tool.  A tool id that does
        not belong to the service propagates the service layer's
        :class:`ValueError`, mapped to HTTP 400 by the global handler.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    tool = mcp_registry.set_tool_enabled(
        factory,
        service_id=service_id,
        workspace_id=workspace_id,
        tool_id=tool_id,
        enabled=bool(body.get("enabled")),
    )
    return {"tool": tool}


@router.delete("/api/admin/mcp-services/{service_id}/tools/{tool_id}")
async def delete_mcp_tool(request: Request, service_id: int, tool_id: int) -> dict[str, Any]:
    """Remove one tool from a service's inventory.

    Args:
        request: Incoming FastAPI request.
        service_id: Primary key of the owning service.
        tool_id: Primary key of the tool.

    Returns:
        ``{"deleted": <bool>}``.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "deleted": mcp_registry.delete_tool(
            factory, service_id=service_id, workspace_id=workspace_id, tool_id=tool_id
        )
    }
