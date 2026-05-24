"""HTML pages for the agents surface."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.agent._agents import Agent

router = APIRouter(tags=["agents"])


@router.get("/agents", response_class=HTMLResponse, response_model=None)
async def agents_index_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the workspace-wide agent index page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/agents", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/agents_index.html",
        {"active_page": "agents", "is_admin": user["is_admin"]},
    )


@router.get("/agents/{slug}", response_class=HTMLResponse, response_model=None)
async def agent_profile_page(slug: str, request: Request) -> HTMLResponse | RedirectResponse:
    """Render an individual agent's profile page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url=f"/auth/login?next=/agents/{slug}", status_code=303)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        agent = session.execute(
            select(Agent).where(Agent.workspace_id == workspace_id, Agent.slug == slug)
        ).scalar_one_or_none()
    if agent is None:
        raise ResourceNotFoundError("agent not found.")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/agent_profile.html",
        {
            "active_page": "agents",
            "is_admin": user["is_admin"],
            "current_user_id": user["id"],
            "agent": {
                "slug": agent.slug,
                "display_name": agent.display_name,
                "avatar_kind": agent.avatar_kind,
            },
        },
    )
