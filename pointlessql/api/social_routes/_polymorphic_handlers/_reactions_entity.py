"""Entity-level reaction handlers.

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
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    ALLOWED_EMOJI,
    resolve_target_id,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.models.social._social_reaction import SocialReaction
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

# ---------------------------------------------------------------------------
# Entity-level reactions (Phase 77.8.C UNIQUE + 77.8.D handlers)
# ---------------------------------------------------------------------------


def validate_emoji_field(emoji: str | None) -> str:
    """Normalise + validate a reaction emoji against the GitHub-6 set."""
    if not emoji or emoji not in ALLOWED_EMOJI:
        raise BadRequestError(f"emoji must be one of {ALLOWED_EMOJI}")
    return emoji


async def list_polymorphic_reactions(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return aggregated entity-level reactions for a polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "reactions": [...]}`` where
        each row is ``{"emoji", "count", "has_current_user_reacted"}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    del workspace_id
    factory = request.app.state.session_factory

    with factory() as session:
        rows = session.execute(
            select(
                SocialReaction.emoji,
                SocialReaction.user_id,
            ).where(SocialReaction.social_target_id == target_id)
        ).all()

    counts: dict[str, int] = {e: 0 for e in ALLOWED_EMOJI}
    mine: set[str] = set()
    for emoji_row, uid in rows:
        if emoji_row in counts:
            counts[emoji_row] += 1
        if uid == user["id"]:
            mine.add(emoji_row)

    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "reactions": [
            {
                "emoji": e,
                "count": counts[e],
                "has_current_user_reacted": e in mine,
            }
            for e in ALLOWED_EMOJI
        ],
    }


async def apply_polymorphic_reaction(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Add an emoji reaction on a polymorphic entity (Phase 77.8.D).

    Idempotency is enforced by the
    ``uq_dp_reactions_polymorphic`` UNIQUE constraint that 77.8.C
    added (legacy DP-id PK is unable to dedupe rows with NULL
    ``data_product_id``).  Re-applying the same emoji no-ops.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "emoji", "added": bool}``.
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
        try:
            session.add(
                SocialReaction(
                    workspace_id=workspace_id,
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
            action="audit.reaction.dp_added",
            entity_kind=kind,
            entity_ref=ref,
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )

    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "emoji": emoji,
        "added": added,
    }


async def remove_polymorphic_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's emoji reaction on a polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        emoji: The emoji to remove (must be in the allow-list).
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "emoji", "removed": bool}``.
    """
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory
    emoji = validate_emoji_field(emoji)

    removed = False
    with factory() as session:
        result = session.execute(
            _delete(SocialReaction).where(
                SocialReaction.social_target_id == target_id,
                SocialReaction.user_id == user["id"],
                SocialReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.dp_removed",
            entity_kind=kind,
            entity_ref=ref,
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "emoji": emoji,
        "removed": removed,
    }


