"""Admin surface for App Spaces — governance grouping of hosted apps.

Define API scopes once for a group of hosted apps, assign apps into a
space, and read each app's effective scopes.  The enforcement of those
scopes is layered by the grant / policy stack; this surface is the
declaration + assignment console.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services import app_hosting, app_spaces

router = APIRouter(tags=["admin-app-spaces"])


@router.get("/admin/app-spaces", response_class=HTMLResponse)
async def admin_app_spaces_index(request: Request) -> HTMLResponse:
    """Render the App Spaces console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_app_spaces.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_app_spaces.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/app-spaces")
async def list_app_spaces(request: Request) -> dict[str, Any]:
    """Return the workspace's app spaces plus its hosted apps."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    apps = [
        {"id": app.id, "slug": app.slug, "title": app.title, "app_space_id": app.app_space_id}
        for app in app_hosting.list_apps(factory, workspace_id=workspace_id)
    ]
    return {
        "spaces": app_spaces.list_spaces(factory, workspace_id=workspace_id),
        "apps": apps,
    }


@router.post("/api/admin/app-spaces")
async def create_app_space(
    request: Request, body: dict[str, Any] = Body(default_factory=dict[str, Any])
) -> dict[str, Any]:
    """Create an app space.

    Args:
        request: Incoming FastAPI request.
        body: JSON with ``name`` and optional ``description`` /
            ``api_scopes`` (list).  A blank or duplicate name propagates
            the service's :class:`ValidationError` (HTTP 400).

    Returns:
        ``{"space": {...}}`` with the created space.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    created_by = get_user(request)["email"] or None
    space = app_spaces.create_space(
        factory,
        workspace_id=workspace_id,
        name=str(body.get("name") or ""),
        description=(str(body["description"]) if body.get("description") else None),
        api_scopes=_scope_list(body.get("api_scopes")),
        created_by=created_by,
    )
    return {"space": space}


@router.patch("/api/admin/app-spaces/{space_id}")
async def update_app_space(
    request: Request, space_id: int, body: dict[str, Any] = Body(default_factory=dict[str, Any])
) -> dict[str, Any]:
    """Update a space's description and/or API scopes.

    Args:
        request: Incoming FastAPI request.
        space_id: Target space.
        body: JSON with optional ``description`` and/or ``api_scopes``.

    Returns:
        ``{"space": {...}}`` with the updated space.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    # An absent key leaves the field unchanged; an explicit JSON ``null``
    # (or empty string) clears it — so map null to "" rather than letting
    # str(None) persist the literal text "None".
    if "description" in body:
        raw_description = body["description"]
        description = "" if raw_description is None else str(raw_description)
    else:
        description = None
    space = app_spaces.update_space(
        factory,
        space_id=space_id,
        workspace_id=workspace_id,
        description=description,
        api_scopes=_scope_list(body["api_scopes"]) if "api_scopes" in body else None,
    )
    return {"space": space}


@router.delete("/api/admin/app-spaces/{space_id}")
async def delete_app_space(request: Request, space_id: int) -> dict[str, Any]:
    """Delete an app space (member apps are ungrouped)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "deleted": app_spaces.delete_space(factory, space_id=space_id, workspace_id=workspace_id)
    }


@router.post("/api/admin/app-spaces/assign")
async def assign_app_to_space(
    request: Request, body: dict[str, Any] = Body(default_factory=dict[str, Any])
) -> dict[str, Any]:
    """Assign a hosted app to a space (or detach it).

    Args:
        request: Incoming FastAPI request.
        body: JSON with ``app_id`` and ``space_id`` (``null`` detaches).
            An unknown app/space propagates the service's
            :class:`ValidationError` (HTTP 400).

    Returns:
        The assignment result from :func:`app_spaces.assign_app`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return app_spaces.assign_app(
        factory,
        workspace_id=workspace_id,
        app_id=int(body.get("app_id", 0)),
        space_id=_optional_space_id(body.get("space_id")),
    )


def _optional_space_id(raw: Any) -> int | None:
    """Coerce a request-body ``space_id`` into an int, or ``None`` to detach.

    ``null`` and ``""`` mean "detach the app from any space"; a number
    or numeric string names the target space.  Any other value is a
    client error rather than a silent detach, so it is rejected.

    Args:
        raw: The raw ``space_id`` value from the request body.

    Returns:
        The target space id, or ``None`` to detach.

    Raises:
        ValidationError: When *raw* is neither blank nor coercible to an
            integer.
    """
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("space_id must be an integer or null") from exc


def _scope_list(value: Any) -> list[str]:
    """Coerce a request-body ``api_scopes`` value into a list of strings."""
    if isinstance(value, list):
        return [str(item) for item in cast("list[Any]", value)]
    return []
