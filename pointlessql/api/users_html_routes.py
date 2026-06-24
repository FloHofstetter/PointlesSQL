"""HTML pages for the user-directory surface.

Three routes:

* ``GET /users`` — workspace-scoped People index.
* ``GET /users/me`` — 302 to the caller's own profile page.
* ``GET /users/{user_id}`` — renders ``pages/user_profile.html``
  which Alpine-fetches the full payload from
  ``GET /api/users/{user_id}/profile``.

Anonymous visitors are bounced to ``/auth/login?next=...`` so the
deep-link survives the OIDC round-trip.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, select

from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.models.workspace._core import WorkspaceMember

router = APIRouter(tags=["users"])


@router.get("/users", response_class=HTMLResponse, response_model=None)
async def users_index_page(
    request: Request,
    role: str | None = None,
    recent: int | None = None,
) -> HTMLResponse | RedirectResponse:
    """Render the People index — workspace members + role chips.

    Workspace-scoped: only members of the caller's currently-active
    workspace are listed.  The ``role`` query-param filters by
    ``admin`` / ``supervisor`` / ``auditor`` / ``member``; absence
    shows everyone.  ``recent=1`` orders by most-recently-logged-in.

    Args:
        request: Starlette request carrying the auth cookie + the
            ``workspace_id`` middleware annotation.
        role: Optional role filter.  Accepts ``admin``, ``supervisor``,
            ``auditor``, ``member``.  Unknown values match nothing.
        recent: ``1`` to order by ``last_seen_at`` desc; default
            order is by display name.

    Returns:
        ``HTMLResponse`` with ``pages/users_index.html`` rendered,
        or a 303 redirect to ``/auth/login`` for anonymous callers.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/users", status_code=303)
    workspace_id = int(getattr(request.state, "workspace_id", 0) or 0)

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            select(
                User.id,
                User.email,
                User.display_name,
                User.is_admin,
                User.is_supervisor,
                User.is_auditor,
                User.created_at,
            )
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        if role == "admin":
            stmt = stmt.where(User.is_admin.is_(True))
        elif role == "supervisor":
            stmt = stmt.where(User.is_supervisor.is_(True))
        elif role == "auditor":
            stmt = stmt.where(User.is_auditor.is_(True))
        elif role == "member":
            stmt = stmt.where(User.is_admin.is_(False))
        if recent == 1:
            # No last_seen_at column yet; fall back to most-recently
            # registered as a proxy for "recently active" until
            # session-level tracking is added.
            stmt = stmt.order_by(desc(User.created_at))
        else:
            stmt = stmt.order_by(User.display_name, User.email)
        rows = session.execute(stmt).all()
    users: list[dict[str, Any]] = [
        {
            "id": int(r[0]),
            "email": r[1],
            "display_name": r[2] or r[1],
            "is_admin": bool(r[3]),
            "is_supervisor": bool(r[4]),
            "is_auditor": bool(r[5]),
            "registered_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/users_index.html",
        {
            "active_page": "users",
            "users": users,
            "role_filter": role,
            "recent": recent,
        },
    )


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
        return RedirectResponse(url=f"/auth/login?next=/users/{user_id}", status_code=303)

    factory = request.app.state.session_factory
    with factory() as session:
        target = session.execute(
            select(User.id, User.email, User.display_name).where(User.id == user_id)
        ).first()
    if target is None:
        raise ResourceNotFoundError("user not found.")

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
