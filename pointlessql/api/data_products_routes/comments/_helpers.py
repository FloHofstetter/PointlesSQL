"""Comment-row helpers: thread-depth walk, reaction aggregation, serialization."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from pointlessql.api.data_products_routes.comments._constants import (
    ALLOWED_EMOJI,
    BODY_PREVIEW_LEN,
    MAX_THREAD_DEPTH,
)
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment


def body_preview(body_md: str) -> str:
    """Truncate a comment body for the audit-log detail JSON."""
    snippet = body_md.strip().replace("\n", " ")
    if len(snippet) > BODY_PREVIEW_LEN:
        return snippet[: BODY_PREVIEW_LEN - 1] + "…"
    return snippet


def chain_depth(session: Any, parent_id: int) -> int:
    """Return the depth of the existing reply chain ending at *parent_id*.

    Depth 1 = top-level comment, depth 2 = a single reply, etc.
    Walks up via ``parent_comment_id`` with a hard ceiling so a
    pathological self-loop in the data can't blow up the request.
    """
    depth = 1
    current_id: int | None = parent_id
    while current_id is not None and depth <= MAX_THREAD_DEPTH + 1:
        parent = session.get(DataProductComment, current_id)
        if parent is None or parent.parent_comment_id is None:
            return depth
        current_id = parent.parent_comment_id
        depth += 1
    return depth


def collect_reactions(
    session: Any, comment_ids: list[int], caller_user_id: int
) -> dict[int, list[dict[str, Any]]]:
    """Return per-comment reaction aggregates.

    Args:
        session: Open SQLAlchemy session.
        comment_ids: PKs to aggregate.
        caller_user_id: Used to set the per-emoji
            ``has_current_user_reacted`` flag.

    Returns:
        ``{comment_id: [{emoji, count, has_current_user_reacted}]}``.
        Comments with no reactions get an entry with zero counts on
        every emoji so the UI doesn't have to special-case missing
        keys.
    """
    if not comment_ids:
        return {}
    rows = session.execute(
        select(
            DataProductCommentReaction.comment_id,
            DataProductCommentReaction.emoji,
            DataProductCommentReaction.user_id,
        ).where(DataProductCommentReaction.comment_id.in_(comment_ids))
    ).all()
    counts: dict[int, dict[str, int]] = {}
    mine: dict[int, set[str]] = {}
    for cid, emoji, uid in rows:
        counts.setdefault(cid, {e: 0 for e in ALLOWED_EMOJI})
        if emoji in counts[cid]:
            counts[cid][emoji] += 1
        if uid == caller_user_id:
            mine.setdefault(cid, set()).add(emoji)
    result: dict[int, list[dict[str, Any]]] = {}
    for cid in comment_ids:
        per = counts.get(cid, {e: 0 for e in ALLOWED_EMOJI})
        mine_set = mine.get(cid, set())
        result[cid] = [
            {
                "emoji": e,
                "count": per[e],
                "has_current_user_reacted": e in mine_set,
            }
            for e in ALLOWED_EMOJI
        ]
    return result


def serialise_comment(
    row: DataProductComment,
    *,
    author_email: str | None,
    author_display_name: str | None,
    body_md_resolved: str,
    reactions: list[dict[str, Any]] | None = None,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one comment row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "parent_comment_id": row.parent_comment_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        # Phase 76.5 — when the comment is authored by an agent
        # the ``agent`` payload carries the slug + display name;
        # ``author.user_id`` is None in that case.
        "agent": agent,
        "body_md": "" if row.deleted_at else row.body_md,
        # Phase 76.7 — cite-token render projection.  Carries the
        # same string as ``body_md`` with ``#dp:`` / ``#topic:`` /
        # ``#user:`` / ``#agent:`` tokens replaced by markdown
        # anchors.  The frontend reads this field via the
        # ``pqlRenderCitations`` helper.
        "body_md_resolved": body_md_resolved,
        "mentioned_user_ids": json.loads(row.mentioned_user_ids_json or "[]"),
        "category": row.category,
        "is_accepted_answer": bool(row.is_accepted_answer),
        "reactions": reactions if reactions is not None else [],
        "created_at": row.created_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }
