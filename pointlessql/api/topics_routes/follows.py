"""``/api/topics/{slug}/follow``.

Two endpoints — idempotent POST + DELETE — backing the topic-
follow toggle on ``/topics/{slug}`` and the eligibility check on
the per-user feed .
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.social._topic import Topic, UserTopicFollow

router = APIRouter(tags=["topics"])


def _resolve_topic(session: Any, workspace_id: int, slug: str) -> Topic:
    """Return the topic row or raise 404 enriched with workspace-known slugs."""
    topic = session.execute(
        select(Topic).where(Topic.workspace_id == workspace_id, Topic.slug == slug)
    ).scalar_one_or_none()
    if topic is None:
        # enrich the 404 with the workspace's known
        # topic slugs so callers see "did you mean…?" alternatives
        # instead of a bare "not found".
        known = list(
            session.execute(select(Topic.slug).where(Topic.workspace_id == workspace_id)).scalars()
        )
        raise ResourceNotFoundError.not_found(
            what=f"topic {slug!r}",
            alternatives=known,
            hint="See /topics for the full list.",
        )
    return topic


@router.post("/api/topics/{slug}/follow")
async def follow_topic(slug: str, request: Request) -> dict[str, Any]:
    """Follow a topic.  Idempotent.

    Args:
        slug: URL-safe topic identifier.
        request: Incoming FastAPI request.

    Returns:
        ``{"slug": str, "added": bool}``.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    added = False
    with factory() as session:
        topic = _resolve_topic(session, workspace_id, slug)
        try:
            session.add(
                UserTopicFollow(
                    user_id=caller["id"],
                    topic_id=topic.id,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
            added = True
        except IntegrityError:
            session.rollback()
            added = False
    return {"slug": slug, "added": added}


@router.delete("/api/topics/{slug}/follow")
async def unfollow_topic(slug: str, request: Request) -> dict[str, Any]:
    """Unfollow a topic.  Idempotent.

    Args:
        slug: URL-safe topic identifier.
        request: Incoming FastAPI request.

    Returns:
        ``{"slug": str, "removed": bool}``.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    removed = False
    with factory() as session:
        topic = _resolve_topic(session, workspace_id, slug)
        result = session.execute(
            delete(UserTopicFollow).where(
                UserTopicFollow.user_id == caller["id"],
                UserTopicFollow.topic_id == topic.id,
            )
        )
        session.commit()
        removed = bool(result.rowcount)
    return {"slug": slug, "removed": removed}
