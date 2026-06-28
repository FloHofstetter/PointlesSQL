"""The Agent page + admin lifecycle controls for the Hermes dashboard.

``GET /agent`` renders the iframe shell that embeds the reverse-proxied
Hermes dashboard.  The three ``/api/hermes/*`` endpoints let an admin
read the managed instance's status and start / stop it without a
PointlesSQL restart — useful when Hermes was installed after start-up
or needs a clean bounce.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.services.hermes import HermesStartupError

router = APIRouter(tags=["hermes"])


@router.get("/agent", response_class=HTMLResponse, response_model=None)
async def agent_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render ``/agent`` — the embedded Hermes dashboard.

    Anonymous callers are sent to login; authenticated non-admins get the
    standard 403 "Access denied" envelope (the dashboard can run commands,
    so it is admin-only, matching the proxy gate and the ``/admin`` pages —
    a silent redirect home read as the page being broken).
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/agent", status_code=303)
    require_admin(request)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/agent_hermes.html",
        {"active_page": "agent", "is_admin": user["is_admin"]},
    )


@router.get("/api/hermes/status")
async def api_hermes_status(request: Request) -> dict[str, Any]:
    """Return the managed-instance status snapshot (admin-only)."""
    require_admin(request)
    manager = getattr(request.app.state, "hermes_manager", None)
    if manager is None:
        return {"enabled": False, "mode": None, "running": False, "healthy": False}
    return await manager.status()


@router.post("/api/hermes/start")
async def api_hermes_start(request: Request) -> dict[str, Any]:
    """Start the shared managed instance if it is not already running.

    Admin-only.  A no-op in external mode (nothing to spawn) and when
    an instance is already up.

    Args:
        request: Incoming FastAPI request.

    Returns:
        dict: The refreshed status snapshot.

    Raises:
        HermesStartupError: 503 when Hermes is disabled or the spawn
            fails.
    """
    require_admin(request)
    manager = getattr(request.app.state, "hermes_manager", None)
    if manager is None:
        raise HermesStartupError("Hermes is not enabled. Set POINTLESSQL_HERMES_ENABLED=1.")
    if manager.is_managed and manager.resolve() is None:
        await manager.start_shared()
    return await manager.status()


@router.post("/api/hermes/stop")
async def api_hermes_stop(request: Request) -> dict[str, Any]:
    """Stop every managed instance (admin-only)."""
    require_admin(request)
    manager = getattr(request.app.state, "hermes_manager", None)
    if manager is None:
        raise HermesStartupError("Hermes is not enabled. Set POINTLESSQL_HERMES_ENABLED=1.")
    await manager.stop_all()
    return await manager.status()
