"""Genie Ontology routes — lineage-authority ranking + table suggestions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import current_workspace_id
from pointlessql.api.genie_routes._shared import ensure_space
from pointlessql.services import genie as genie_service

router = APIRouter()


@router.get("/api/genie/ontology/authority")
async def api_table_authority(request: Request) -> dict[str, Any]:
    """Return the workspace's lineage-ranked table authority scores.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"tables": [...], "total": int}`` — tables ranked by a
        PageRank-style authority over the lineage table graph.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    tables = genie_service.compute_table_authority(factory, workspace_id=workspace_id)
    return {"tables": tables, "total": len(tables)}


@router.get("/api/genie/spaces/{slug}/suggested-tables")
async def api_suggested_tables(request: Request, slug: str) -> dict[str, Any]:
    """Suggest top-authority tables a space has not yet curated.

    Args:
        request: Incoming FastAPI request.
        slug: Space slug.

    Returns:
        ``{"suggestions": [...]}`` — ranked tables not already in the
        space's curated list, for one-click context auto-population.
    """
    space = ensure_space(request, slug)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    suggestions = genie_service.suggest_tables_for_space(
        factory,
        workspace_id=workspace_id,
        curated=genie_service.space_tables(space),
    )
    return {"suggestions": suggestions}
