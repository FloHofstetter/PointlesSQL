"""Hosted-apps HTML pages — list at ``/apps``, detail at ``/apps/<slug>``.

Two HTML routes for any signed-in user; the JSON lifecycle surface
they drive lives in :mod:`pointlessql.api.apps_routes` and the
runtime traffic flows through :mod:`pointlessql.api.apps_proxy`.
The pages receive the active workspace's app rows server-side
(projected to the exact shape ``GET /api/apps`` answers) so the
table paints without a fetch round-trip and the Alpine factories
can swap in refreshed rows without reshaping.

NOTE: this router is intentionally **not registered** yet.  The
navigation integration wires it into
``pointlessql/api/_bootstrap/_routers.py`` next to the
``apps_routes`` JSON router (``app.include_router(...)``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.apps_routes import serialize_app
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    require_workspace_admin,
)
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.services import app_hosting

router = APIRouter(tags=["apps-html"])


def _can_admin(request: Request) -> bool:
    """Return whether the caller may mutate apps in this workspace.

    The page uses this to decide whether to render the create form
    and the source editor — the JSON routes re-check on every
    mutation, so this is presentation-only.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` for tenant admins and workspace-local admins.
    """
    try:
        require_workspace_admin(request)
    except AuthorizationError:
        return False
    return True


@router.get("/apps", response_class=HTMLResponse)
async def apps_page(request: Request):
    """Render the hosted-apps list (create form + app table)."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = app_hosting.list_apps(factory, workspace_id=workspace_id)
    manager = getattr(request.app.state, "apps_manager", None)
    return get_templates(request).TemplateResponse(
        request,
        "pages/apps.html",
        {
            "active_page": "apps",
            "apps": [serialize_app(row, manager=manager) for row in rows],
            "can_admin": _can_admin(request),
        },
    )


@router.get("/apps/{slug}", response_class=HTMLResponse)
async def app_detail_page(request: Request, slug: str):
    """Render one app's cockpit (iframe + lifecycle + logs + source).

    Args:
        request: Incoming FastAPI request.
        slug: App slug from the URL.

    Returns:
        The rendered detail page.

    Raises:
        ResourceNotFoundError: When no app with *slug* exists in the
            active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = app_hosting.get_app(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"App '{slug}' not found.")
    manager = getattr(request.app.state, "apps_manager", None)
    return get_templates(request).TemplateResponse(
        request,
        "pages/app_detail.html",
        {
            "active_page": "apps",
            "app": serialize_app(row, manager=manager),
            "can_admin": _can_admin(request),
        },
    )
