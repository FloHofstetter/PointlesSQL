"""Admin surface for Genie bot connectors (Teams / M365 Copilot).

Register an outbound chat bot, mint and rotate its shared-secret token
(shown once), bind it to a Genie space, and enable/disable it.  The
inbound webhook (``/api/genie/teams/{public_id}/messages``) authenticates
against the token minted here and answers through the grant-enforced
Genie path.
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
from pointlessql.services import genie as genie_service
from pointlessql.services import genie_connectors

router = APIRouter(tags=["admin-genie-connectors"])


@router.get("/admin/genie-connectors", response_class=HTMLResponse)
async def admin_genie_connectors_index(request: Request) -> HTMLResponse:
    """Render the Genie connectors console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_genie_connectors.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_genie_connectors.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/genie-connectors")
async def list_genie_connectors(request: Request) -> dict[str, Any]:
    """Return the workspace's connectors plus its Genie spaces."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    spaces = [
        {"slug": space.slug, "title": space.title}
        for space in genie_service.list_spaces(factory, workspace_id=workspace_id)
    ]
    return {
        "connectors": genie_connectors.list_connectors(factory, workspace_id=workspace_id),
        "spaces": spaces,
    }


@router.post("/api/admin/genie-connectors")
async def create_genie_connector(
    request: Request, body: dict[str, Any] = Body(default_factory=dict[str, Any])
) -> dict[str, Any]:
    """Register a connector and return its one-time token.

    Args:
        request: Incoming FastAPI request.
        body: JSON with ``name`` and optional ``platform`` /
            ``genie_space_slug``.  A blank/duplicate name or an unknown
            platform propagates the service's :class:`ValidationError`.

    Returns:
        ``{"connector": {...}, "token": "<plaintext>"}`` — the token is
        shown only here.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    created_by = get_user(request)["email"] or None
    connector, token = genie_connectors.create_connector(
        factory,
        workspace_id=workspace_id,
        name=str(body.get("name") or ""),
        platform=(str(body["platform"]) if body.get("platform") else None),
        genie_space_slug=(str(body["genie_space_slug"]) if body.get("genie_space_slug") else None),
        created_by=created_by,
    )
    return {"connector": connector, "token": token}


@router.patch("/api/admin/genie-connectors/{connector_id}")
async def update_genie_connector(
    request: Request,
    connector_id: int,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Update a connector's platform, bound space, and/or enabled flag.

    Args:
        request: Incoming FastAPI request.
        connector_id: Target connector.
        body: JSON with optional ``platform``, ``genie_space_slug``
            (``null`` unbinds), and/or ``enabled``.

    Returns:
        ``{"connector": {...}}`` with the updated connector.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    # Only forward the space binding when the key is present, so the
    # service's "leave unchanged" sentinel applies otherwise.
    slug_kwargs: dict[str, Any] = {}
    if "genie_space_slug" in body:
        raw = body["genie_space_slug"]
        slug_kwargs["genie_space_slug"] = str(raw) if raw is not None else None
    connector = genie_connectors.update_connector(
        factory,
        connector_id=connector_id,
        workspace_id=workspace_id,
        platform=(str(body["platform"]) if body.get("platform") else None),
        enabled=(bool(body["enabled"]) if "enabled" in body else None),
        **slug_kwargs,
    )
    return {"connector": connector}


@router.post("/api/admin/genie-connectors/{connector_id}/rotate")
async def rotate_genie_connector_token(request: Request, connector_id: int) -> dict[str, Any]:
    """Rotate a connector's shared secret and return the new token."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    connector, token = genie_connectors.rotate_token(
        factory, connector_id=connector_id, workspace_id=workspace_id
    )
    return {"connector": connector, "token": token}


@router.delete("/api/admin/genie-connectors/{connector_id}")
async def delete_genie_connector(request: Request, connector_id: int) -> dict[str, Any]:
    """Delete a connector."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "deleted": genie_connectors.delete_connector(
            factory, connector_id=connector_id, workspace_id=workspace_id
        )
    }
