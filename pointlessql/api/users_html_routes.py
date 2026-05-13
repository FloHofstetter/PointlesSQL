"""HTML pages for the user-directory surface (Phase 76.2).

Two routes:

* ``GET /users/me`` — 302 to the caller's own profile page.
* ``GET /users/{user_id}`` — renders ``pages/user_profile.html``
  which Alpine-fetches the full payload from
  ``GET /api/users/{user_id}/profile``.

Anonymous visitors are bounced to ``/auth/login?next=...`` so the
deep-link survives the OIDC round-trip.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import get_user
from pointlessql.models.auth import User

router = APIRouter(tags=["users"])


@router.get("/users/me", response_class=HTMLResponse, response_model=None)
async def my_profile_redirect(request: Request) -> RedirectResponse:
    """Redirect ``/users/me`` to the caller's profile page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/users/me", status_code=303)
    return RedirectResponse(url=f"/users/{user['id']}", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse, response_model=None)
async def user_profile_page(
    user_id: int,
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the per-user profile page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/users/{user_id}", status_code=303
        )

    factory = request.app.state.session_factory
    with factory() as session:
        target = session.execute(
            select(User.id, User.email, User.display_name).where(
                User.id == user_id
            )
        ).first()
    if target is None:
        # bare-http-ok: profile target must exist.
        raise HTTPException(status_code=404, detail="user not found")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/user_profile.html",
        {
            "active_page": "users",
            "is_admin": user["is_admin"],
            "current_user_id": user["id"],
            "target_user": {
                "user_id": int(target[0]),
                "email": target[1],
                "display_name": target[2],
            },
        },
    )
