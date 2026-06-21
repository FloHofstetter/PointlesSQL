"""JSON sibling of the agent-memory registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.agent_memory_registry_routes._shared import build_registry

router = APIRouter()


@router.get("/api/agent-memories")
async def agent_memories_api(
    request: Request,
    q: str = Query(default="", description="Filter agents by id substring."),
) -> dict[str, Any]:
    """Return the agent-memory registry as JSON for machine consumers.

    Mirrors the shape the HTML page is rendered from so a client can
    page the same registry without scraping the table.

    Args:
        request: Incoming FastAPI request.
        q: Optional case-insensitive substring filter on the agent id.

    Returns:
        ``{"agents", "total", "query"}``.
    """
    return build_registry(request, query=q.strip() or None)
