"""Glossary term-relation + term-graph endpoints (F4).

Admin can declare relations; any-user can read the graph drawer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api.dependencies import get_user, require_admin, require_user
from pointlessql.exceptions import BadRequestError
from pointlessql.services import glossary as glossary_service

router = APIRouter(tags=["glossary"])


@router.post("/api/glossary/{term_id}/relations")
async def add_relation(
    term_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Add a relation from *term_id* to another term (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    user = get_user(request)
    target = body.get("target_term_id")
    kind = str(body.get("kind", "related"))
    if not isinstance(target, int):
        raise BadRequestError("target_term_id must be an integer")
    try:
        result = glossary_service.add_relation(
            factory,
            source_term_id=term_id,
            target_term_id=target,
            kind=kind,
            created_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"relation": result}


@router.delete("/api/glossary/{term_id}/relations/{relation_id}")
async def delete_relation(term_id: int, relation_id: int, request: Request) -> dict[str, Any]:
    """Delete one relation (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    removed = glossary_service.delete_relation(factory, relation_id=relation_id)
    if not removed:
        # bare-http-ok: 404 for unknown relation PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="relation not found")
    return {"deleted": True}


@router.get("/api/glossary/{term_id}/relations")
async def list_relations(term_id: int, request: Request, direction: str = "both") -> dict[str, Any]:
    """Return relations incident on *term_id* (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    return {
        "relations": glossary_service.list_relations(factory, term_id=term_id, direction=direction)
    }


@router.get("/api/glossary/{term_id}/graph")
async def get_term_graph(term_id: int, request: Request, depth: int = 2) -> dict[str, Any]:
    """Return the bounded knowledge-graph rooted at *term_id*."""
    require_user(request)
    factory = request.app.state.session_factory
    if depth <= 0 or depth > 5:
        raise BadRequestError("depth must be in [1, 5]")
    try:
        result = glossary_service.term_graph(factory, root_term_id=term_id, depth=depth)
    except LookupError as exc:
        # bare-http-ok: 404 for unknown root term; no domain exception needed.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result
