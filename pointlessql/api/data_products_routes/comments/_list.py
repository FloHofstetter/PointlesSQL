"""``GET /api/data-products/{catalog}/{schema}/comments`` — threaded list."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api._social_serializers import agent_payload
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.comments._helpers import (
    collect_reactions,
    serialise_comment,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.social import resolve_citations

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/comments")
async def list_data_product_comments(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return every live comment for the product in threaded order.

    A soft-deleted top-level comment with no live children is
    omitted; a soft-deleted parent whose replies are still live
    is rendered as a placeholder so the reply chain stays
    coherent.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "comments": [...]}`` flattened
        in (parent_id, created_at) order.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductComment)
                .where(
                    DataProductComment.workspace_id == workspace_id,
                    DataProductComment.data_product_id == row.id,
                )
                .order_by(
                    DataProductComment.parent_comment_id.nulls_first(),
                    DataProductComment.created_at,
                )
            )
            .scalars()
            .all()
        )
        author_ids = {c.author_user_id for c in rows}
        author_map: dict[int, tuple[str, str]] = {}
        if author_ids:
            users = (
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}
        agent_ids = {
            c.author_agent_id for c in rows if c.author_agent_id is not None
        }
        agent_map: dict[int, dict[str, Any] | None] = {}
        if agent_ids:
            agents = (
                session.execute(select(Agent).where(Agent.id.in_(agent_ids)))
                .scalars()
                .all()
            )
            agent_map = {a.id: agent_payload(a) for a in agents}
        reactions_by_comment = collect_reactions(
            session, [c.id for c in rows], user["id"]
        )

    live_children_by_parent: dict[int, int] = {}
    for c in rows:
        if c.parent_comment_id is not None and c.deleted_at is None:
            live_children_by_parent[c.parent_comment_id] = (
                live_children_by_parent.get(c.parent_comment_id, 0) + 1
            )

    payload: list[dict[str, Any]] = []
    for c in rows:
        if c.deleted_at is not None and not live_children_by_parent.get(c.id):
            # Soft-deleted leaf — drop entirely.
            continue
        author_email, author_display = author_map.get(
            c.author_user_id, (None, None)
        )
        comment_agent_payload = (
            agent_map.get(c.author_agent_id)
            if c.author_agent_id is not None
            else None
        )
        body_md_resolved = (
            ""
            if c.deleted_at
            else resolve_citations(c.body_md, factory, workspace_id)
        )
        payload.append(
            serialise_comment(
                c,
                author_email=author_email,
                author_display_name=author_display,
                body_md_resolved=body_md_resolved,
                agent=comment_agent_payload,
                reactions=reactions_by_comment.get(c.id),
            )
        )

    return {"data_product_id": row.id, "comments": payload}
