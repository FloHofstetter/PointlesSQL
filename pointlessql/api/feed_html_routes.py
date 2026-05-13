"""HTML pages for the per-user feed + settings (Phase 76.4)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user

router = APIRouter(tags=["feed"])


@router.get("/feed", response_class=HTMLResponse, response_model=None)
async def feed_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render ``/feed`` — per-user merged activity stream."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/feed", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/feed.html",
        {"active_page": "feed", "is_admin": user["is_admin"]},
    )


@router.get(
    "/settings/notifications", response_class=HTMLResponse, response_model=None
)
async def notification_settings_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the per-event-type notification-preferences settings page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/settings/notifications", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/settings_notifications.html",
        {"active_page": "settings", "is_admin": user["is_admin"]},
    )
