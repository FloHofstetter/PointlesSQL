"""``/api/agents/{slug}/profile`` — agent detail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment

router = APIRouter(tags=["agents"])


@router.get("/api/agents/{slug}/profile")
async def agent_profile(slug: str, request: Request) -> dict[str, Any]:
    """Return an agent's profile + recent activity + run-stats.

    Args:
        slug: Agent identifier.
        request: Incoming FastAPI request.

    Returns:
        ``{"agent": {...}, "recent_comments": [...], "run_stats":
        {count}}``.

    Raises:
        ResourceNotFoundError: When no agent in the workspace has
            that slug.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        agent = session.execute(
            select(Agent).where(Agent.workspace_id == workspace_id, Agent.slug == slug)
        ).scalar_one_or_none()
        if agent is None:
            raise ResourceNotFoundError("agent not found.")
        principal = session.get(User, agent.principal_user_id)
        recent_comments = (
            session.execute(
                select(DataProductComment)
                .where(
                    DataProductComment.author_agent_id == agent.id,
                    DataProductComment.deleted_at.is_(None),
                )
                .order_by(DataProductComment.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        # AgentRun rows carry a free-form ``agent_id`` text field —
        # we match on slug as the conventional handle.  Existing
        # historical runs may not match (no FK), which is fine.
        run_count = int(
            session.execute(
                select(func.count()).select_from(AgentRun).where(AgentRun.agent_id == slug)
            ).scalar_one()
        )

    return {
        "agent": {
            "id": agent.id,
            "slug": agent.slug,
            "display_name": agent.display_name,
            "avatar_kind": agent.avatar_kind,
            "avatar_url": agent.avatar_url,
            "home_url": agent.home_url,
            "is_verified": bool(agent.is_verified),
            "bio_md": agent.bio_md,
            "principal": {
                "user_id": agent.principal_user_id,
                "email": principal.email if principal else None,
                "display_name": principal.display_name if principal else None,
            },
        },
        "recent_comments": [
            {
                "id": c.id,
                "data_product_id": c.data_product_id,
                "body_md": c.body_md,
                "category": c.category,
                "created_at": c.created_at.isoformat(),
            }
            for c in recent_comments
        ],
        "run_stats": {"count": run_count},
    }
