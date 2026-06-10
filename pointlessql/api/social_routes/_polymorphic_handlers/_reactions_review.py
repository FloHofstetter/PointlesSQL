"""Per-review reaction handlers.

Mirrors the per-comment reaction handlers, keyed on ``review_id``.
Reviews of one product share that product's social anchor, so the
reaction key is the review PK — otherwise every sibling review of the
same product would move as a single count.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._reactions_entity import (
    aggregate_reactions,
    reactor_names,
    validate_emoji_field,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    resolve_target_id,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.catalog._data_product_review_reaction import (
    DataProductReviewReaction,
)
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.services.social.audit_mirror import mirror_social_to_audit


def load_review_on_target(
    session: Any, review_id: int, *, workspace_id: int, target_id: int
) -> DataProductReview:
    """Return the review row that belongs to the addressed social target.

    The review must live in the same workspace and reference the same
    ``social_target_id`` as the kind/ref the caller addressed (reviews
    anchor on their parent product's target).
    """
    review = session.get(DataProductReview, review_id)
    if (
        review is None
        or review.workspace_id != workspace_id
        or review.social_target_id != target_id
    ):
        raise ResourceNotFoundError.not_found(what=f"review id={review_id}")
    return review


async def apply_polymorphic_review_reaction(
    kind: str, ref: str, review_id: int, request: Request
) -> dict[str, Any]:
    """Add an emoji reaction to a review.

    Idempotent: re-applying the same ``(review, user, emoji)`` triple
    is a no-op.

    Args:
        kind: Entity kind discriminator of the review's parent.
        ref: Opaque entity reference within *kind*.
        review_id: PK of the review being reacted to.
        request: Incoming FastAPI request.

    Returns:
        ``{"review_id", "emoji", "added": bool}``.
    """
    from sqlalchemy.exc import IntegrityError

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    payload = await request.json()
    emoji = validate_emoji_field(payload.get("emoji"))

    added = False
    with factory() as session:
        load_review_on_target(session, review_id, workspace_id=workspace_id, target_id=target_id)
        try:
            session.add(
                DataProductReviewReaction(
                    review_id=review_id,
                    social_target_id=target_id,
                    user_id=user["id"],
                    emoji=emoji,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
            added = True
        except IntegrityError:
            session.rollback()
            added = False

    if added:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.review_added",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"review-{review_id}",
            detail={"review_id": review_id, "emoji": emoji},
            workspace_id=workspace_id,
        )

    return {"review_id": review_id, "emoji": emoji, "added": added}


async def remove_polymorphic_review_reaction(
    kind: str, ref: str, review_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's emoji reaction on a review.

    Args:
        kind: Entity kind discriminator of the review's parent.
        ref: Opaque entity reference within *kind*.
        review_id: PK of the review.
        emoji: The emoji to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"review_id", "emoji", "removed": bool}``.
    """
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory
    emoji = validate_emoji_field(emoji)

    removed = False
    with factory() as session:
        load_review_on_target(session, review_id, workspace_id=workspace_id, target_id=target_id)
        result = session.execute(
            _delete(DataProductReviewReaction).where(
                DataProductReviewReaction.review_id == review_id,
                DataProductReviewReaction.user_id == user["id"],
                DataProductReviewReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.review_removed",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"review-{review_id}",
            detail={"review_id": review_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
    return {"review_id": review_id, "emoji": emoji, "removed": removed}


async def list_polymorphic_review_reactions(
    kind: str, ref: str, review_id: int, request: Request
) -> dict[str, Any]:
    """Return aggregated reaction counts for a review.

    Args:
        kind: Entity kind discriminator of the review's parent.
        ref: Opaque entity reference within *kind*.
        review_id: PK of the review.
        request: Incoming FastAPI request.

    Returns:
        ``{"review_id", "reactions": [{emoji, count,
        has_current_user_reacted}, ...]}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with_names = bool(request.query_params.get("with_names"))
    with factory() as session:
        load_review_on_target(session, review_id, workspace_id=workspace_id, target_id=target_id)
        rows = session.execute(
            select(
                DataProductReviewReaction.emoji,
                DataProductReviewReaction.user_id,
            ).where(DataProductReviewReaction.review_id == review_id)
        ).all()
        names = reactor_names(session, {int(uid) for _, uid in rows}) if with_names else None

    return {
        "review_id": review_id,
        "reactions": aggregate_reactions(rows, user["id"], names),
    }
