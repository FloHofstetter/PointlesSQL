"""Per-comment reaction handlers.

Extracted from the 2231-LOC ``_polymorphic_handlers.py`` monolith
in Phase 89.1 — each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
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
    validate_emoji_field,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    ALLOWED_EMOJI,
    resolve_target_id,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.social.entity_registry import (
    url_for as registry_url_for,
)

# ---------------------------------------------------------------------------
# Comment reactions (Phase 78 polish — polymorphism unlock)
# ---------------------------------------------------------------------------


def load_comment_on_target(
    session: Any, comment_id: int, *, workspace_id: int, target_id: int
) -> DataProductComment:
    """Return the live comment row that belongs to the social target.

    The comment must live in the same workspace and reference the
    same ``social_target_id`` as the kind/ref the caller addressed.
    Soft-deleted comments are treated as missing.
    """
    comment = session.get(DataProductComment, comment_id)
    if (
        comment is None
        or comment.workspace_id != workspace_id
        or comment.social_target_id != target_id
        or comment.deleted_at is not None
    ):
        raise ResourceNotFoundError.not_found(what=f"comment id={comment_id}")
    return comment


async def apply_polymorphic_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Add an emoji reaction to a comment on any entity kind.

    Idempotent: re-applying the same triple is a no-op.  The
    comment author is pinged via :func:`fanout_event` regardless
    of kind (mirrors the DP-only path landed in Phase 76.1).

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment being reacted to.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "emoji", "added": bool}``.
    """
    from sqlalchemy.exc import IntegrityError

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    payload = await request.json()
    emoji = validate_emoji_field(payload.get("emoji"))

    added = False
    comment_author_id: int | None = None
    dp_back_pointer: int | None = None
    with factory() as session:
        comment = load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        comment_author_id = int(comment.author_user_id)
        dp_back_pointer = (
            int(comment.data_product_id)
            if kind == "dp" and comment.data_product_id is not None
            else None
        )
        try:
            session.add(
                DataProductCommentReaction(
                    comment_id=comment_id,
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
            action="audit.reaction.comment_added",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
        if comment_author_id != user["id"]:
            source_url = (
                f"{registry_url_for(kind, ref)}"
                f"#tab-discussion-comment-{comment_id}"
            )
            summary = (
                f"@{user.get('email') or 'someone'} reacted "
                f"{emoji} to your comment on {ref}"
            )
            fanout_event(
                factory,
                event_type="pointlessql.data_product.comment_reacted",
                entity_kind=kind,
                entity_ref=ref,
                workspace_id=workspace_id,
                actor_user_id=user["id"],
                source_url=source_url,
                summary_md=summary,
                data_product_id=dp_back_pointer,
                extra_recipients=[comment_author_id],
            )

    return {"comment_id": comment_id, "emoji": emoji, "added": added}


async def remove_polymorphic_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's emoji reaction on a comment.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment.
        emoji: The emoji to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "emoji", "removed": bool}``.
    """
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory
    emoji = validate_emoji_field(emoji)

    removed = False
    with factory() as session:
        load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        result = session.execute(
            _delete(DataProductCommentReaction).where(
                DataProductCommentReaction.comment_id == comment_id,
                DataProductCommentReaction.user_id == user["id"],
                DataProductCommentReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.comment_removed",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
    return {"comment_id": comment_id, "emoji": emoji, "removed": removed}


async def list_polymorphic_comment_reactions(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Return aggregated reaction counts for a comment on any kind.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "reactions": [{emoji, count,
        has_current_user_reacted}, ...]}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        rows = session.execute(
            select(
                DataProductCommentReaction.emoji,
                DataProductCommentReaction.user_id,
            ).where(DataProductCommentReaction.comment_id == comment_id)
        ).all()

    counts: dict[str, int] = {e: 0 for e in ALLOWED_EMOJI}
    mine: set[str] = set()
    for emoji_row, uid in rows:
        if emoji_row in counts:
            counts[emoji_row] += 1
        if uid == user["id"]:
            mine.add(emoji_row)

    return {
        "comment_id": comment_id,
        "reactions": [
            {
                "emoji": e,
                "count": counts[e],
                "has_current_user_reacted": e in mine,
            }
            for e in ALLOWED_EMOJI
        ],
    }


