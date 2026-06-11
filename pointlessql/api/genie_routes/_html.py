"""HTML pages for Genie spaces (list + room shells, Alpine-hydrated)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, get_user
from pointlessql.api.genie_routes._shared import ensure_space

router = APIRouter()


@router.get("/genie", response_class=HTMLResponse)
async def genie_spaces_page(request: Request):
    """Render the Genie spaces list page."""
    return get_templates(request).TemplateResponse(
        request,
        "pages/genie_spaces.html",
        {"active_page": "genie"},
    )


@router.get("/genie/{slug}", response_class=HTMLResponse)
async def genie_space_page(request: Request, slug: str):
    """Render one Genie room (chat + curated sidebar + config drawer).

    Args:
        request: Incoming FastAPI request.
        slug: Space slug from the URL.

    Returns:
        The server-rendered shell; transcript, assets, and config
        hydrate client-side through the JSON surface.
    """
    space = ensure_space(request, slug)
    user = get_user(request)
    can_edit = bool(user["is_admin"]) or int(user["id"]) == space.owner_id
    return get_templates(request).TemplateResponse(
        request,
        "pages/genie_space.html",
        {
            "active_page": "genie",
            "space": {
                "slug": space.slug,
                "title": space.title,
                "description": space.description,
            },
            "can_edit": can_edit,
        },
    )
