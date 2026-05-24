"""Follower count / list / follow / unfollow.

Each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    resolve_target_id,
)
from pointlessql.models.auth import User
from pointlessql.models.social._social_follow import SocialFollow

# ---------------------------------------------------------------------------
# Followers
# ---------------------------------------------------------------------------


async def get_polymorphic_followers_count(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the follower count + caller-following flag.

    Counts rows on the polymorphic ``social_follows`` table for
    ``social_target_id == target_id``.  The ``following`` flag
    reports whether the caller has an outstanding follow row.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"count": int, "following": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        count = session.execute(
            select(func.count(SocialFollow.user_id)).where(
                SocialFollow.workspace_id == workspace_id,
                SocialFollow.social_target_id == target_id,
            )
        ).scalar_one()
        mine = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
    return {"count": int(count), "following": mine is not None}


async def list_polymorphic_followers(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the follower roster for the polymorphic entity.

    The list is gated to the caller themselves + workspace admins —
    privacy mirrors the DP follower list.  Non-admin callers see an
    empty ``followers`` array but accurate ``count``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "followers": [...]}`` where
        each follower entry carries ``user_id``, ``email``,
        ``display_name`` and the ``created_at`` of the follow row.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        is_admin = bool(user.get("is_admin"))
        if not is_admin:
            return {
                "entity_kind": kind,
                "entity_ref": ref,
                "followers": [],
            }
        rows = session.execute(
            select(SocialFollow, User)
            .join(User, User.id == SocialFollow.user_id)
            .where(
                SocialFollow.workspace_id == workspace_id,
                SocialFollow.social_target_id == target_id,
            )
            .order_by(SocialFollow.created_at.desc())
        ).all()
    followers = [
        {
            "user_id": user_row.id,
            "email": user_row.email,
            "display_name": user_row.display_name,
            "created_at": follow.created_at.isoformat(),
        }
        for follow, user_row in rows
    ]
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "followers": followers,
    }


async def follow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently follow a polymorphic entity.

    Writes one row to ``social_follows``.  Repeat POSTs no-op via
    the composite-PK ``(workspace_id, social_target_id, user_id)``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed": True, "already": bool}`` — ``already`` is
        true on the second consecutive POST.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
        if existing is not None:
            return {"followed": True, "already": True}
        session.add(
            SocialFollow(
                workspace_id=workspace_id,
                social_target_id=target_id,
                user_id=user["id"],
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return {"followed": True, "already": False}


async def unfollow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently unfollow a polymorphic entity.

    Drops the matching ``social_follows`` row if present.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed": False, "removed": bool}`` — ``removed`` is
        true on the call that actually dropped a row.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
        if existing is None:
            return {"followed": False, "removed": False}
        session.delete(existing)
        session.commit()
    return {"followed": False, "removed": True}


