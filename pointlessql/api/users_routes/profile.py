"""``/api/users/{user_id}/profile`` — user profile.

Two endpoints:

* ``GET`` — returns the user's bio + badges + stewarded DPs +
  follow counts + recent activity snapshot.  Anyone authenticated
  in the workspace may read.
* ``PUT`` — owner (the user themselves) or install-admin may
  update.  Body keys: ``bio_md``, ``avatar_url``, ``location``,
  ``links_json``.  Each is optional; absent keys leave the
  current value alone.

The ``UserProfile`` row is lazily created on first PUT — a GET
that finds no row renders the default empty profile so we don't
have to seed one for every existing user at migration time.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._user_badge import UserBadge
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.models.social._user_profile import UserProfile

router = APIRouter(tags=["users"])

_LINKS_MAX = 8
_BIO_MAX = 4000


def _serialise_profile(
    user: User,
    profile: UserProfile | None,
) -> dict[str, Any]:
    """Render a ``UserProfile`` row as a JSON-friendly dict."""
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "bio_md": profile.bio_md if profile else "",
        "avatar_url": profile.avatar_url if profile else None,
        "location": profile.location if profile else None,
        "links": json.loads(profile.links_json) if profile else [],
        "updated_at": profile.updated_at.isoformat() if profile else None,
    }


@router.get("/api/users/{user_id}/profile")
async def get_user_profile(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return the user's profile + counts + badges + recent activity.

    Args:
        user_id: PK of the user.
        request: Incoming FastAPI request.

    Returns:
        ``{"profile": {...}, "counts": {followers, following,
        stewarded_dps, comments_30d, reviews}, "badges": [...]
        , "recent_activity": [...]}``.

    Raises:
        HTTPException: 404 when the target user does not exist.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ResourceNotFoundError.not_found(what=f"user id={user_id}")
        profile = session.get(UserProfile, user_id)

        followers_count = int(
            session.execute(
                select(func.count())
                .select_from(UserFollow)
                .where(UserFollow.followed_user_id == user_id)
            ).scalar_one()
        )
        following_count = int(
            session.execute(
                select(func.count())
                .select_from(UserFollow)
                .where(UserFollow.follower_user_id == user_id)
            ).scalar_one()
        )
        stewarded = session.execute(
            select(DataProduct.id, DataProduct.catalog_name, DataProduct.schema_name)
            .where(DataProduct.steward_user_id == user_id)
            .order_by(DataProduct.catalog_name, DataProduct.schema_name)
        ).all()
        comments_30d_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
        comments_30d = int(
            session.execute(
                select(func.count())
                .select_from(DataProductComment)
                .where(
                    DataProductComment.author_user_id == user_id,
                    DataProductComment.created_at >= comments_30d_cutoff,
                    DataProductComment.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        reviews_count = int(
            session.execute(
                select(func.count())
                .select_from(DataProductReview)
                .where(DataProductReview.author_user_id == user_id)
            ).scalar_one()
        )
        badge_rows = (
            session.execute(
                select(UserBadge).where(UserBadge.user_id == user_id).order_by(UserBadge.awarded_at)
            )
            .scalars()
            .all()
        )

        recent_comments = (
            session.execute(
                select(DataProductComment)
                .where(
                    DataProductComment.author_user_id == user_id,
                    DataProductComment.deleted_at.is_(None),
                )
                .order_by(DataProductComment.created_at.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )
        recent_reviews = (
            session.execute(
                select(DataProductReview)
                .where(DataProductReview.author_user_id == user_id)
                .order_by(DataProductReview.created_at.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )
        viewer = get_user(request)
        viewer_follows = (
            session.execute(
                select(UserFollow).where(
                    UserFollow.follower_user_id == viewer["id"],
                    UserFollow.followed_user_id == user_id,
                )
            ).first()
            is not None
        )

    return {
        "profile": _serialise_profile(user, profile),
        "counts": {
            "followers": followers_count,
            "following": following_count,
            "stewarded_dps": len(stewarded),
            "comments_30d": comments_30d,
            "reviews": reviews_count,
        },
        "stewarded_dps": [
            {"id": did, "catalog": cat, "schema": sch} for did, cat, sch in stewarded
        ],
        "badges": [
            {
                "badge_key": b.badge_key,
                "awarded_at": b.awarded_at.isoformat(),
                "awarded_for_count": b.awarded_for_count,
            }
            for b in badge_rows
        ],
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
        "recent_reviews": [
            {
                "id": r.id,
                "data_product_id": r.data_product_id,
                "stars": r.stars,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent_reviews
        ],
        "viewer_follows": viewer_follows,
    }


@router.put("/api/users/{user_id}/profile")
async def update_user_profile(
    user_id: int,
    request: Request,
) -> dict[str, Any]:
    """Update the caller's profile (or any profile when admin).

    Args:
        user_id: PK of the profile to update.
        request: Incoming FastAPI request.

    Returns:
        Serialised :func:`_serialise_profile` payload.

    Raises:
        AuthorizationError: When the caller is not the owner and
            not install-admin.
        HTTPException: 400 on oversized bio / too many link rows;
            404 when the target user does not exist.
    """
    require_user(request)
    caller = get_user(request)
    if user_id != caller["id"] and not caller.get("is_admin"):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="update_profile",
            securable_type="user_profile",
            full_name=str(user_id),
        )

    body = await request.json()
    bio_md = body.get("bio_md")
    avatar_url = body.get("avatar_url")
    location = body.get("location")
    links = body.get("links")

    if bio_md is not None and not isinstance(bio_md, str):
        raise BadRequestError("bio_md must be a string")
    if bio_md is not None and len(bio_md) > _BIO_MAX:
        raise BadRequestError(f"bio_md exceeds {_BIO_MAX} chars")
    if links is not None:
        if not isinstance(links, list):
            raise BadRequestError(f"links must be a list of at most {_LINKS_MAX} entries")
        if len(links) > _LINKS_MAX:  # pyright: ignore[reportUnknownArgumentType]
            raise BadRequestError(f"links must be a list of at most {_LINKS_MAX} entries")
        for entry in links:  # pyright: ignore[reportUnknownVariableType]
            if (
                not isinstance(entry, dict)
                or "url" not in entry
                or not isinstance(entry.get("url"), str)  # pyright: ignore[reportUnknownMemberType]
            ):
                raise BadRequestError("each link must be an object with a 'url' string")

    now = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        target = session.get(User, user_id)
        if target is None:
            raise ResourceNotFoundError.not_found(what=f"user id={user_id}")
        profile = session.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                bio_md=bio_md or "",
                avatar_url=avatar_url,
                location=location,
                links_json=json.dumps(links) if links is not None else "[]",
                updated_at=now,
            )
            session.add(profile)
        else:
            if bio_md is not None:
                profile.bio_md = bio_md
            if avatar_url is not None:
                profile.avatar_url = avatar_url
            if location is not None:
                profile.location = location
            if links is not None:
                profile.links_json = json.dumps(links)
            profile.updated_at = now
        session.commit()
        session.refresh(profile)
        return _serialise_profile(target, profile)
