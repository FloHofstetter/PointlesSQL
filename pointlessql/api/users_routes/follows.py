"""``/api/users/{user_id}/follow`` — user-to-user follows.

Three endpoints:

* ``POST`` — idempotent follow.  Self-follow is rejected app-side
  (DB-level CHECK is the belt-and-braces guard).
* ``DELETE`` — idempotent unfollow.
* ``GET /followers`` + ``GET /following`` — listing.

Each ``POST`` emits ``pointlessql.user.followed`` (recipient =
the followed user) so the inbox + Phase-20 SIEM forwarder both
pick up the social signal.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services import audit as audit_service
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_USER_FOLLOWED,
    emit_governance_event,
)

router = APIRouter(tags=["users"])

_AUDIT_FOLLOW = "audit.user.followed"
_AUDIT_UNFOLLOW = "audit.user.unfollowed"


@router.post("/api/users/{user_id}/follow")
async def follow_user(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Follow another user.  Idempotent.

    Args:
        user_id: PK of the user to follow.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed_user_id": int, "added": bool}``.

    Raises:
        BadRequestError: On a self-follow attempt.
        ResourceNotFoundError.not_found: When the target user does
            not exist.
    """
    require_user(request)
    caller = get_user(request)
    if user_id == caller["id"]:
        raise BadRequestError("cannot follow yourself")
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    added = False
    with factory() as session:
        target = session.get(User, user_id)
        if target is None:
            raise ResourceNotFoundError.not_found(what=f"user id={user_id}")
        try:
            session.add(
                UserFollow(
                    follower_user_id=caller["id"],
                    followed_user_id=user_id,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
            added = True
        except IntegrityError:
            session.rollback()
            added = False

    if added:
        audit_service.log_action(
            factory,
            user_id=caller["id"],
            user_email=caller.get("email", ""),
            action=_AUDIT_FOLLOW,
            target=f"user:{user_id}",
            detail={"followed_user_id": user_id},
            workspace_id=workspace_id,
        )
        # Per-user inbox row for the followed user.
        try:
            with factory() as session:
                session.add(
                    UserNotification(
                        workspace_id=workspace_id,
                        recipient_user_id=user_id,
                        event_type=EVENT_TYPE_USER_FOLLOWED,
                        source_data_product_id=None,
                        source_url=f"/users/{caller['id']}",
                        summary_md=(f"@{caller.get('email') or 'someone'} started following you"),
                        actor_user_id=caller["id"],
                        created_at=datetime.datetime.now(datetime.UTC),
                    )
                )
                session.commit()
        # bare-broad-ok: inbox fan-out is best-effort — a
        # transient DB error must not abort the surrounding POST
        # handler that already committed the follow row.
        except Exception:  # noqa: BLE001 — inbox fan-out is best-effort.
            pass
        await emit_governance_event(
            EVENT_TYPE_USER_FOLLOWED,
            {
                "follower_user_id": caller["id"],
                "followed_user_id": user_id,
            },
            settings=request.app.state.settings,
            session_factory=factory,
            workspace_id=workspace_id,
        )
    return {"followed_user_id": user_id, "added": added}


@router.delete("/api/users/{user_id}/follow")
async def unfollow_user(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Unfollow another user.  Idempotent.

    Args:
        user_id: PK of the user to unfollow.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed_user_id": int, "removed": bool}``.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    removed = False
    with factory() as session:
        result = session.execute(
            delete(UserFollow).where(
                UserFollow.follower_user_id == caller["id"],
                UserFollow.followed_user_id == user_id,
            )
        )
        session.commit()
        removed = bool(result.rowcount)
    if removed:
        audit_service.log_action(
            factory,
            user_id=caller["id"],
            user_email=caller.get("email", ""),
            action=_AUDIT_UNFOLLOW,
            target=f"user:{user_id}",
            detail={"followed_user_id": user_id},
            workspace_id=workspace_id,
        )
    return {"followed_user_id": user_id, "removed": removed}


@router.get("/api/users/{user_id}/followers")
async def list_followers(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return the list of users following *user_id*.

    Args:
        user_id: PK of the user whose followers we are listing.
        request: Incoming FastAPI request.

    Returns:
        ``{"user_id": int, "followers": [{user_id, email,
        display_name}, ...]}``.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.execute(
            select(User.id, User.email, User.display_name)
            .join(UserFollow, UserFollow.follower_user_id == User.id)
            .where(UserFollow.followed_user_id == user_id)
            .order_by(User.display_name)
        ).all()
    return {
        "user_id": user_id,
        "followers": [
            {"user_id": int(uid), "email": email, "display_name": display_name}
            for uid, email, display_name in rows
        ],
    }


@router.get("/api/users/{user_id}/following")
async def list_following(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return the list of users *user_id* is following.

    Args:
        user_id: PK of the user whose follow-set we are listing.
        request: Incoming FastAPI request.

    Returns:
        ``{"user_id": int, "following": [{user_id, email,
        display_name}, ...]}``.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.execute(
            select(User.id, User.email, User.display_name)
            .join(UserFollow, UserFollow.followed_user_id == User.id)
            .where(UserFollow.follower_user_id == user_id)
            .order_by(User.display_name)
        ).all()
    return {
        "user_id": user_id,
        "following": [
            {"user_id": int(uid), "email": email, "display_name": display_name}
            for uid, email, display_name in rows
        ],
    }
