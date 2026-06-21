"""HTML page route for the agent-memory registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.agent_memory_registry_routes._shared import build_registry
from pointlessql.api.dependencies import get_templates

router = APIRouter()


@router.get("/agent-memories", response_class=HTMLResponse)
async def agent_memories_page(
    request: Request,
    q: str = Query(default="", description="Filter agents by id substring."),
) -> HTMLResponse:
    """Render the registry of agents that have left a memory trail.

    The landing page for agent memory: one row per ``agent_id`` with its
    run / operation counts and latest activity, each linking into the
    existing ``/memory/{agent_id}`` brain browser.  ``active_page`` is
    ``agents`` so it shares the People context panel with ``/agents``.

    Args:
        request: Incoming FastAPI request.
        q: Optional case-insensitive substring filter on the agent id.

    Returns:
        The rendered ``pages/agent_memories.html`` response.
    """
    data = build_registry(request, query=q.strip() or None)
    ctx: dict[str, Any] = {
        "agents": data["agents"],
        "total": data["total"],
        "query": data["query"],
        "active_page": "agents",
        "active_catalog": None,
        "active_schema": None,
        "active_table": None,
    }
    return get_templates(request).TemplateResponse(request, "pages/agent_memories.html", ctx)
