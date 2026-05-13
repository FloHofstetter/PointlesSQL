"""``/api/topics`` — list + create topics (Phase 76.3).

Two endpoints:

* ``GET /api/topics`` — paginated listing.  Sortable by DP-count
  (default, descending), follower-count, or alphabetic on
  display name.
* ``POST /api/topics`` — steward / install-admin may create a new
  topic.  Slug auto-derived from display name, deduped per
  workspace with a numeric suffix on collision.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.api.topics_routes._slug import slugify
from pointlessql.models.social._topic import (
    DataProductTopic,
    Topic,
    UserTopicFollow,
)
from pointlessql.services import audit as audit_service

router = APIRouter(tags=["topics"])

_AUDIT_TOPIC_CREATED = "audit.topic.created"


def _unique_slug(session: Any, workspace_id: int, base: str) -> str:
    """Return *base* (or ``{base}-N``) free in the workspace."""
    candidate = base
    n = 1
    while True:
        hit = session.execute(
            select(Topic.id).where(
                Topic.workspace_id == workspace_id,
                Topic.slug == candidate,
            )
        ).first()
        if hit is None:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


@router.get("/api/topics")
async def list_topics(
    request: Request,
    sort: str = "dp_count",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the workspace's topics, paginated + sorted.

    Args:
        request: Incoming FastAPI request.
        sort: One of ``dp_count`` (default), ``followers``, or
            ``name``.  Unknown values fall back to ``dp_count``.
        limit: Result-set cap; clamped to ``[1, 200]``.
        offset: Skip count for pagination.

    Returns:
        ``{"sort": str, "topics": [{id, slug, display_name,
        dp_count, follower_count}, ...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    factory = request.app.state.session_factory
    with factory() as session:
        dp_counts = dict(
            session.execute(
                select(
                    DataProductTopic.topic_id, func.count()
                ).group_by(DataProductTopic.topic_id)
            ).all()
        )
        follower_counts = dict(
            session.execute(
                select(
                    UserTopicFollow.topic_id, func.count()
                ).group_by(UserTopicFollow.topic_id)
            ).all()
        )
        rows = (
            session.execute(
                select(Topic)
                .where(Topic.workspace_id == workspace_id)
                .order_by(Topic.display_name)
            )
            .scalars()
            .all()
        )

    payload = [
        {
            "id": t.id,
            "slug": t.slug,
            "display_name": t.display_name,
            "description_md": t.description_md,
            "dp_count": int(dp_counts.get(t.id, 0)),
            "follower_count": int(follower_counts.get(t.id, 0)),
        }
        for t in rows
    ]
    if sort == "followers":
        payload.sort(key=lambda r: int(r["follower_count"] or 0), reverse=True)
    elif sort == "name":
        payload.sort(key=lambda r: str(r["display_name"]).lower())
    else:
        payload.sort(key=lambda r: int(r["dp_count"] or 0), reverse=True)
    return {
        "sort": sort,
        "topics": payload[offset : offset + limit],
        "total": len(payload),
    }


@router.post("/api/topics")
async def create_topic(request: Request) -> dict[str, Any]:
    """Create a new workspace-scoped topic.

    Body: ``{"display_name": str, "description_md": str | None}``.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Serialised topic row.

    Raises:
        HTTPException: 400 on empty display name; 403 if the
            caller is not steward / install-admin.
    """
    require_user(request)
    caller = get_user(request)
    if not (caller.get("is_admin") or caller.get("is_supervisor")):
        # Phase 76.3 scope pick: steward+ may create topics.  We
        # treat "supervisor" + "admin" as the steward+ tier here;
        # plain members read but cannot create new taxonomy.
        # bare-http-ok: tier guard.
        raise HTTPException(
            status_code=403, detail="topic creation requires steward+ role"
        )
    workspace_id = current_workspace_id(request)

    body = await request.json()
    display_name = (body.get("display_name") or "").strip()
    description_md = (body.get("description_md") or "").strip()
    if not display_name:
        # bare-http-ok: display_name is required.
        raise HTTPException(
            status_code=400, detail="display_name is required"
        )

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        slug = _unique_slug(session, workspace_id, slugify(display_name))
        topic = Topic(
            workspace_id=workspace_id,
            slug=slug,
            display_name=display_name[:80],
            description_md=description_md,
            created_at=now,
            created_by_user_id=caller["id"],
        )
        session.add(topic)
        session.commit()
        session.refresh(topic)
        topic_id = topic.id
        topic_slug = topic.slug

    audit_service.log_action(
        factory,
        user_id=caller["id"],
        user_email=caller.get("email", ""),
        action=_AUDIT_TOPIC_CREATED,
        target=f"topic:{topic_slug}",
        detail={"topic_id": topic_id, "display_name": display_name},
        workspace_id=workspace_id,
    )

    return {
        "id": topic_id,
        "slug": topic_slug,
        "display_name": display_name,
        "description_md": description_md,
        "dp_count": 0,
        "follower_count": 0,
    }
