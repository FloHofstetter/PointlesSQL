"""The home surface — ``GET /`` renders the activity feed.

The landing page is the per-user activity stream (the same template
``/feed`` renders), so the first thing a user sees is everything that
needs their attention: social activity, approvals, and data-health
signals in one filterable feed. ``/feed`` stays as an alias so older
links and bookmarks keep resolving.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_templates, get_user

router = APIRouter(tags=["home"])


@router.get("/", response_class=HTMLResponse, response_model=None)
async def home_index(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the home feed — the per-user merged activity stream."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/", status_code=303)
    return get_templates(request).TemplateResponse(
        request,
        "pages/feed.html",
        {"active_page": "feed", "is_admin": user["is_admin"]},
    )
