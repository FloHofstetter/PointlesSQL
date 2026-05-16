"""Star get / star / unstar / list-user-stars.

Extracted from the 2231-LOC ``_polymorphic_handlers.py`` monolith
in Phase 89.1 — each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import desc, func, select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    resolve_target_id,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.social._social_star import SocialStar
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

# ---------------------------------------------------------------------------
# Stars (Phase 77.8)
# ---------------------------------------------------------------------------


async def get_polymorphic_star(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the star count for the entity + whether caller starred it.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"starred": bool, "count": int}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()
        mine = session.get(
            SocialStar,
            {
                "workspace_id": workspace_id,
                "user_id": user["id"],
                "social_target_id": target_id,
            },
        )
    return {"starred": mine is not None, "count": int(count)}


async def star_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently star a polymorphic entity (Phase 77.8).

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"starred": True, "count": int}`` — the updated count
        reflects the post-write state.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialStar,
            {
                "workspace_id": workspace_id,
                "user_id": user["id"],
                "social_target_id": target_id,
            },
        )
        first_star = existing is None
        if first_star:
            session.add(
                SocialStar(
                    workspace_id=workspace_id,
                    user_id=user["id"],
                    social_target_id=target_id,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()

    if first_star:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.star.added",
            entity_kind=kind,
            entity_ref=ref,
            detail={},
            workspace_id=workspace_id,
        )
    return {"starred": True, "count": int(count)}


async def unstar_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently unstar a polymorphic entity (Phase 77.8)."""
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        result = session.execute(
            _delete(SocialStar).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.user_id == user["id"],
                SocialStar.social_target_id == target_id,
            )
        )
        session.commit()
        removed = bool(result.rowcount)
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.star.removed",
            entity_kind=kind,
            entity_ref=ref,
            detail={},
            workspace_id=workspace_id,
        )
    return {"starred": False, "count": int(count)}


async def list_user_stars(
    user_id: int, request: Request, kind: str | None = None, limit: int = 50
) -> dict[str, Any]:
    """Return the starred-entity list for a given user.

    Args:
        user_id: Target user whose stars to list.  Only the caller
            themselves or an admin may list anyone else's stars.
        request: Incoming FastAPI request.
        kind: Optional filter to a single entity kind.
        limit: Max number of rows to return.

    Returns:
        ``{"user_id", "count", "stars": [...]}``.

    Raises:
        AuthorizationError: When the caller is not the target user
            and not an admin.
    """
    from pointlessql.models.social._social_target import SocialTarget

    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    if caller["id"] != user_id and not bool(caller.get("is_admin")):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="stars-list",
            securable_type="user",
            full_name=str(user_id),
        )

    with factory() as session:
        stmt = (
            select(SocialStar, SocialTarget)
            .join(SocialTarget, SocialTarget.id == SocialStar.social_target_id)
            .where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.user_id == user_id,
            )
            .order_by(desc(SocialStar.created_at))
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(SocialTarget.entity_kind == kind)
        rows = session.execute(stmt).all()
    stars = [
        {
            "entity_kind": target.entity_kind,
            "entity_ref": target.entity_ref,
            "starred_at": star.created_at.isoformat(),
        }
        for star, target in rows
    ]
    return {"user_id": user_id, "count": len(stars), "stars": stars}


