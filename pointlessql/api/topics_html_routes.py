"""HTML pages for the topics surface (Phase 76.3).

Two routes:

* ``GET /topics`` — workspace-wide topic index.
* ``GET /topics/{slug}`` — per-topic detail.

Both bounce anonymous visitors to ``/auth/login?next=...``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.social._topic import Topic

router = APIRouter(tags=["topics"])


@router.get("/topics", response_class=HTMLResponse, response_model=None)
async def topics_index_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the workspace-wide topic index page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/topics", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/topics_index.html",
        {"active_page": "topics", "is_admin": user["is_admin"]},
    )


@router.get("/topics/{slug}", response_class=HTMLResponse, response_model=None)
async def topic_detail_page(
    slug: str, request: Request
) -> HTMLResponse | RedirectResponse:
    """Render the topic-detail page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/topics/{slug}", status_code=303
        )
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        topic = session.execute(
            select(Topic).where(
                Topic.workspace_id == workspace_id, Topic.slug == slug
            )
        ).scalar_one_or_none()
    if topic is None:
        raise ResourceNotFoundError(f"topic {slug!r} not found.")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/topic_detail.html",
        {
            "active_page": "topics",
            "is_admin": user["is_admin"],
            "current_user_id": user["id"],
            "topic": {
                "id": topic.id,
                "slug": topic.slug,
                "display_name": topic.display_name,
                "description_md": topic.description_md,
            },
        },
    )
