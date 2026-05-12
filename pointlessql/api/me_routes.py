"""Per-user settings routes (Phase 71.4).

One HTML page (``/me/settings``) + two JSON endpoints
(``GET / PUT /api/me/settings``) for self-service preferences.
Today the surface only carries the marketplace-digest opt-in;
future preferences extend the same payload without a new route.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.models.auth import User

router = APIRouter(tags=["me"])


def _serialise_settings(user_row: User) -> dict[str, Any]:
    """Render the caller's settings as a JSON-friendly dict."""
    return {
        "email": user_row.email,
        "display_name": user_row.display_name,
        "digest_email_optin": bool(user_row.digest_email_optin),
    }


@router.get("/me/settings", response_class=HTMLResponse, response_model=None)
async def me_settings_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the self-service settings form."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/me/settings", status_code=303
        )
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(User, user["id"])
    if row is None:
        return RedirectResponse(url="/auth/login?next=/me/settings", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/me_settings.html",
        {
            "active_page": "me_settings",
            "settings": _serialise_settings(row),
        },
    )


@router.get("/api/me/settings")
async def get_me_settings(request: Request) -> dict[str, Any]:
    """Return the caller's settings."""
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(User, user["id"])
    if row is None:
        # bare-http-ok: middleware should have populated request.state.user
        # already, but if the DB row was deleted out from under the
        # session we surface that as 404 rather than a 500.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="user not found")
    return _serialise_settings(row)


@router.put("/api/me/settings")
async def put_me_settings(request: Request) -> dict[str, Any]:
    """Update the caller's settings.

    Body keys (all optional, missing keys leave the field as-is):

    * ``digest_email_optin`` — bool.
    """
    require_user(request)
    user = get_user(request)
    body = await request.json()
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(User, user["id"])
        if row is None:
            # bare-http-ok: same "user row vanished mid-session" path as the
            # GET; harmless 404 instead of a 500.
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="user not found")
        if "digest_email_optin" in body:
            row.digest_email_optin = bool(body["digest_email_optin"])
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialise_settings(row)
