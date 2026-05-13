"""``/api/data-products/{catalog}/{schema}/(comments/{id}/)?reactions`` (Phase 76.1).

GitHub-style six-emoji reactions on comments + on the product
itself.  Idempotent UPSERT on the composite PK ``(target, user,
emoji)``; ``DELETE`` removes a single emoji while leaving the
caller's other reactions intact.

Fan-out asymmetry: a reaction on a *comment* only notifies the
comment author (anything broader would storm the audit-log with
low-signal rows).  A reaction on the *product* notifies all
followers — same recipient set as the existing
``data_product.commented`` event.  Both axes drop an
``audit.reaction.*`` row alongside the write so Phase-18.7 FTS
picks the rows up in ``/audit/search``.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reaction import DataProductReaction
from pointlessql.services import audit as audit_service
from pointlessql.services.notifications import fanout_dataproduct_event
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_COMMENT_REACTED,
    EVENT_TYPE_DATA_PRODUCT_REACTED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])

ALLOWED_EMOJI: tuple[str, ...] = ("👍", "❤️", "🎉", "😄", "😕", "👀")

_AUDIT_REACTION_COMMENT_ADDED = "audit.reaction.comment_added"
_AUDIT_REACTION_COMMENT_REMOVED = "audit.reaction.comment_removed"
_AUDIT_REACTION_DP_ADDED = "audit.reaction.dp_added"
_AUDIT_REACTION_DP_REMOVED = "audit.reaction.dp_removed"


def _validate_emoji(emoji: str | None) -> str:
    """Reject anything outside the six-emoji canonical set."""
    if not emoji or emoji not in ALLOWED_EMOJI:
        # bare-http-ok: emoji must be one of the canonical six.
        raise HTTPException(
            status_code=400,
            detail=f"emoji must be one of {ALLOWED_EMOJI}",
        )
    return emoji


@router.post("/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions")
async def add_comment_reaction(
    catalog: str,
    schema: str,
    comment_id: int,
    request: Request,
) -> dict[str, Any]:
    """Add an emoji reaction to a comment.

    Idempotent: re-POSTing the same triple is a no-op (no DB
    write, no fan-out).  Reactions on a comment notify the
    comment author only — DP-wide reaction broadcast is a
    separate endpoint.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        comment_id: PK of the comment being reacted to.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id": int, "emoji": str, "added": bool}``.

    Raises:
        HTTPException: 400 on unknown emoji or wrong workspace,
            404 when the comment is missing or soft-deleted.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    payload = await request.json()
    emoji = _validate_emoji(payload.get("emoji"))

    added = False
    comment_author_id: int | None = None
    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.data_product_id != row.id
            or comment.deleted_at is not None
        ):
            # bare-http-ok: target comment must exist + be live.
            raise HTTPException(status_code=404, detail="comment not found")
        comment_author_id = int(comment.author_user_id)

        try:
            session.add(
                DataProductCommentReaction(
                    comment_id=comment_id,
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
        audit_service.log_action(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_AUDIT_REACTION_COMMENT_ADDED,
            target=(
                f"data_product:{catalog}.{schema}#tab-discussion-comment-"
                f"{comment_id}"
            ),
            detail={
                "comment_id": comment_id,
                "emoji": emoji,
            },
            workspace_id=workspace_id,
        )
        if comment_author_id != user["id"]:
            source_url = (
                f"/data-products/{catalog}/{schema}#tab-discussion-comment-"
                f"{comment_id}"
            )
            summary = (
                f"@{user.get('email') or 'someone'} reacted "
                f"{emoji} to your comment on {catalog}.{schema}"
            )
            fanout_dataproduct_event(
                factory,
                event_type=EVENT_TYPE_DATA_PRODUCT_COMMENT_REACTED,
                data_product_id=row.id,
                workspace_id=workspace_id,
                actor_user_id=user["id"],
                source_url=source_url,
                summary_md=summary,
                # Reactions only ping the comment author — the
                # follower fanout path would storm inboxes.
                extra_recipients=[comment_author_id],
            )
        await emit_governance_event(
            EVENT_TYPE_DATA_PRODUCT_COMMENT_REACTED,
            {
                "data_product_id": row.id,
                "data_product_ref": f"{catalog}.{schema}",
                "comment_id": comment_id,
                "emoji": emoji,
                "actor_user_id": user["id"],
                "comment_author_user_id": comment_author_id,
            },
            settings=request.app.state.settings,
            session_factory=factory,
            workspace_id=workspace_id,
        )

    return {"comment_id": comment_id, "emoji": emoji, "added": added}


@router.delete(
    "/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions/{emoji}"
)
async def remove_comment_reaction(
    catalog: str,
    schema: str,
    comment_id: int,
    emoji: str,
    request: Request,
) -> dict[str, Any]:
    """Remove a single emoji reaction from a comment.

    Idempotent: returns ``removed=False`` when no row matched.
    Only touches the caller's own row — never another user's.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        comment_id: PK of the comment.
        emoji: The emoji to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id": int, "emoji": str, "removed": bool}``.

    Raises:
        HTTPException: 400 on unknown emoji, 404 when the comment
            is missing or scoped to a different product.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)
    emoji = _validate_emoji(emoji)

    removed = False
    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.data_product_id != row.id
        ):
            # bare-http-ok: target comment must exist.
            raise HTTPException(status_code=404, detail="comment not found")

        result = session.execute(
            delete(DataProductCommentReaction).where(
                DataProductCommentReaction.comment_id == comment_id,
                DataProductCommentReaction.user_id == user["id"],
                DataProductCommentReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        audit_service.log_action(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_AUDIT_REACTION_COMMENT_REMOVED,
            target=(
                f"data_product:{catalog}.{schema}#tab-discussion-comment-"
                f"{comment_id}"
            ),
            detail={"comment_id": comment_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
    return {"comment_id": comment_id, "emoji": emoji, "removed": removed}


@router.get("/api/data-products/{catalog}/{schema}/comments/{comment_id}/reactions")
async def list_comment_reactions(
    catalog: str,
    schema: str,
    comment_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return aggregated reaction counts for a single comment.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        comment_id: PK of the comment.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id": int, "reactions": [{emoji, count,
        has_current_user_reacted}, ...]}``.

    Raises:
        HTTPException: 404 when the comment is missing or scoped
            to a different product.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.data_product_id != row.id
        ):
            # bare-http-ok: target comment must exist.
            raise HTTPException(status_code=404, detail="comment not found")
        rows = (
            session.execute(
                select(
                    DataProductCommentReaction.emoji,
                    DataProductCommentReaction.user_id,
                ).where(DataProductCommentReaction.comment_id == comment_id)
            )
            .all()
        )

    counts: dict[str, int] = {emoji: 0 for emoji in ALLOWED_EMOJI}
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


@router.post("/api/data-products/{catalog}/{schema}/reactions")
async def add_dp_reaction(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Add an emoji reaction on the product itself.

    Fans out to all followers (same recipient set as the
    ``data_product.commented`` event).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "emoji": str, "added": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    payload = await request.json()
    emoji = _validate_emoji(payload.get("emoji"))

    added = False
    with factory() as session:
        try:
            session.add(
                DataProductReaction(
                    data_product_id=row.id,
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
        audit_service.log_action(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_AUDIT_REACTION_DP_ADDED,
            target=f"data_product:{catalog}.{schema}",
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )
        source_url = f"/data-products/{catalog}/{schema}#tab-discussion"
        summary = (
            f"@{user.get('email') or 'someone'} reacted "
            f"{emoji} to {catalog}.{schema}"
        )
        fanout_dataproduct_event(
            factory,
            event_type=EVENT_TYPE_DATA_PRODUCT_REACTED,
            data_product_id=row.id,
            workspace_id=workspace_id,
            actor_user_id=user["id"],
            source_url=source_url,
            summary_md=summary,
        )
        await emit_governance_event(
            EVENT_TYPE_DATA_PRODUCT_REACTED,
            {
                "data_product_id": row.id,
                "data_product_ref": f"{catalog}.{schema}",
                "emoji": emoji,
                "actor_user_id": user["id"],
            },
            settings=request.app.state.settings,
            session_factory=factory,
            workspace_id=workspace_id,
        )

    return {"data_product_id": row.id, "emoji": emoji, "added": added}


@router.delete("/api/data-products/{catalog}/{schema}/reactions/{emoji}")
async def remove_dp_reaction(
    catalog: str,
    schema: str,
    emoji: str,
    request: Request,
) -> dict[str, Any]:
    """Remove one of the caller's emoji reactions on the product.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        emoji: The emoji to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "emoji": str, "removed": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)
    emoji = _validate_emoji(emoji)

    removed = False
    with factory() as session:
        result = session.execute(
            delete(DataProductReaction).where(
                DataProductReaction.data_product_id == row.id,
                DataProductReaction.user_id == user["id"],
                DataProductReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        audit_service.log_action(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_AUDIT_REACTION_DP_REMOVED,
            target=f"data_product:{catalog}.{schema}",
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )
    return {"data_product_id": row.id, "emoji": emoji, "removed": removed}


@router.get("/api/data-products/{catalog}/{schema}/reactions")
async def list_dp_reactions(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return aggregated DP-level reaction counts."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(
                    DataProductReaction.emoji,
                    DataProductReaction.user_id,
                ).where(DataProductReaction.data_product_id == row.id)
            )
            .all()
        )

    counts: dict[str, int] = {emoji: 0 for emoji in ALLOWED_EMOJI}
    mine: set[str] = set()
    for emoji_row, uid in rows:
        if emoji_row in counts:
            counts[emoji_row] += 1
        if uid == user["id"]:
            mine.add(emoji_row)

    return {
        "data_product_id": row.id,
        "reactions": [
            {
                "emoji": e,
                "count": counts[e],
                "has_current_user_reacted": e in mine,
            }
            for e in ALLOWED_EMOJI
        ],
    }
