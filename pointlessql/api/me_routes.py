"""Per-user routes (Phase 71.4 + 80.5).

Surfaces:

* ``/me`` (Phase 80.5) — consolidated hub landing page that links
  to profile / inbox / subscriptions / settings / API keys.
* ``/me/settings`` (Phase 71.4) — self-service preferences form.
* ``GET / PUT /api/me/settings`` — JSON twin of the settings form.

Today the settings surface only carries the marketplace-digest
opt-in; future preferences extend the same payload without a new
route.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.models.auth import User

router = APIRouter(tags=["me"])


@router.get("/me", response_class=HTMLResponse, response_model=None)
async def me_index_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the consolidated Me hub landing (Phase 80.5).

    Surfaces six tile-cards (Profile · My work · Inbox ·
    Subscriptions · Settings · API keys) so the previously-
    fragmented self-pages are reachable from one place.  Each
    card carries a live count where the underlying model can be
    cheaply aggregated (unread inbox count, dashboards owned,
    API keys held).

    Args:
        request: Starlette request carrying the auth cookie.

    Returns:
        Rendered ``pages/me_index.html``, or a 303 redirect to
        ``/auth/login`` for anonymous callers.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/me", status_code=303)

    user_id = int(user["id"])
    factory = request.app.state.session_factory

    counts: dict[str, int] = {
        "unread_inbox": 0,
        "dashboards_mine": 0,
        "subscriptions": 0,
        "api_keys": 0,
    }
    try:
        from pointlessql.models import ApiKey, Dashboard, UserWebhookSubscription
        from pointlessql.models.notifications import UserNotification

        with factory() as session:
            counts["unread_inbox"] = int(
                session.scalar(
                    select(func.count())
                    .select_from(UserNotification)
                    .where(UserNotification.recipient_user_id == user_id)
                    .where(UserNotification.read_at.is_(None))
                )
                or 0
            )
            counts["dashboards_mine"] = int(
                session.scalar(
                    select(func.count())
                    .select_from(Dashboard)
                    .where(Dashboard.owner_id == user_id)
                )
                or 0
            )
            counts["subscriptions"] = int(
                session.scalar(
                    select(func.count())
                    .select_from(UserWebhookSubscription)
                    .where(UserWebhookSubscription.user_id == user_id)
                )
                or 0
            )
            counts["api_keys"] = int(
                session.scalar(
                    select(func.count())
                    .select_from(ApiKey)
                    .where(ApiKey.created_by_user_id == user_id)
                    .where(ApiKey.revoked_at.is_(None))
                )
                or 0
            )
    except Exception:  # noqa: BLE001 — Me-hub counts are best-effort
        # Empty install or a model missing on an upgrade race: leave
        # counts at zero, render the cards as 0-state.
        pass

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/me_index.html",
        {
            "active_page": "me",
            "me": {
                "id": user_id,
                "email": user.get("email"),
                "display_name": user.get("display_name") or user.get("email"),
                "is_admin": bool(user.get("is_admin")),
            },
            "counts": counts,
        },
    )


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
