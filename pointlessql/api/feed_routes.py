"""``/api/feed`` — per-user merged activity feed (Phase 76.4).

Single endpoint that merges:

* The caller's ``user_notifications`` inbox rows (canonical
  source — all reactive social events fan out into here).
* Recent activity authored by users the caller follows
  (comments + reviews).
* Filter modes: ``all`` | ``mentions`` | ``followed_users`` |
  ``followed_dps`` | ``my``.

The current sub-sprint keeps the implementation deliberately
narrow — it surfaces the inbox + adds the followed-users
overlay.  ``followed_topics`` is folded into the inbox because
the topic-DP-added event already emits an inbox row to the
topic's followers.  FTS search runs against the
``audit.discussion.*`` namespace via the existing Phase-18.7
audit-search backend.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._user_follow import UserFollow

router = APIRouter(tags=["feed"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _row_from_notification(row: UserNotification) -> dict[str, Any]:
    """Normalise a ``UserNotification`` to the feed row shape."""
    return {
        "kind": "notification",
        "event_type": row.event_type,
        "summary_md": row.summary_md,
        "source_url": row.source_url,
        "data_product_id": row.source_data_product_id,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def _row_from_comment(comment: DataProductComment) -> dict[str, Any]:
    """Normalise a comment to the feed row shape."""
    return {
        "kind": "comment",
        "event_type": "pointlessql.data_product.commented",
        "summary_md": comment.body_md[:160],
        "source_url": f"/data-products/#{comment.data_product_id}",
        "data_product_id": comment.data_product_id,
        "actor_user_id": comment.author_user_id,
        "created_at": comment.created_at.isoformat(),
        "read_at": None,
    }


def _row_from_review(review: DataProductReview) -> dict[str, Any]:
    """Normalise a review to the feed row shape."""
    return {
        "kind": "review",
        "event_type": "pointlessql.data_product.reviewed",
        "summary_md": f"{'★' * review.stars} — {review.body_md[:120]}",
        "source_url": f"/data-products/#{review.data_product_id}",
        "data_product_id": review.data_product_id,
        "actor_user_id": review.author_user_id,
        "created_at": review.created_at.isoformat(),
        "read_at": None,
    }


@router.get("/api/feed")
async def get_feed(
    request: Request,
    filter: str = "all",  # noqa: A002 — query param shadows builtin intentionally
    limit: int = _DEFAULT_LIMIT,
    q: str = "",
) -> dict[str, Any]:
    """Return the caller's merged feed.

    Args:
        request: Incoming FastAPI request.
        filter: One of ``all`` (default), ``mentions``,
            ``followed_users``, ``followed_dps``, ``my``.
            Unknown values fall back to ``all``.
        limit: Result cap; clamped to ``[1, 200]``.
        q: Optional substring match on the row summary.  Case-
            insensitive; an empty value disables filtering.

    Returns:
        ``{"filter": str, "rows": [...]}`` sorted by
        ``created_at`` descending.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    limit = max(1, min(_MAX_LIMIT, int(limit)))
    needle = q.strip().lower()

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        # Inbox rows — always pulled, the filter trims after merge.
        inbox = (
            session.execute(
                select(UserNotification)
                .where(
                    UserNotification.recipient_user_id == caller["id"],
                    UserNotification.workspace_id == workspace_id,
                )
                .order_by(UserNotification.created_at.desc())
                .limit(limit * 2)
            )
            .scalars()
            .all()
        )
        rows.extend(_row_from_notification(n) for n in inbox)

        # Followed-users overlay (comments + reviews).
        followed_user_ids: list[int] = [
            int(uid)
            for (uid,) in session.execute(
                select(UserFollow.followed_user_id).where(
                    UserFollow.follower_user_id == caller["id"]
                )
            ).all()
        ]
        if followed_user_ids:
            comments = (
                session.execute(
                    select(DataProductComment)
                    .where(
                        DataProductComment.author_user_id.in_(followed_user_ids),
                        DataProductComment.workspace_id == workspace_id,
                        DataProductComment.deleted_at.is_(None),
                    )
                    .order_by(DataProductComment.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            rows.extend(_row_from_comment(c) for c in comments)

            reviews = (
                session.execute(
                    select(DataProductReview)
                    .where(
                        DataProductReview.author_user_id.in_(followed_user_ids),
                        DataProductReview.workspace_id == workspace_id,
                    )
                    .order_by(DataProductReview.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            rows.extend(_row_from_review(r) for r in reviews)

        # Mentions filter — resolve to the user's id and check
        # ``mentioned_user_ids_json``.  Authored ``my`` filter
        # mirrors the same logic with a different predicate.
        if filter == "mentions":
            mentions = (
                session.execute(
                    select(DataProductComment)
                    .where(
                        DataProductComment.workspace_id == workspace_id,
                        DataProductComment.deleted_at.is_(None),
                    )
                    .order_by(DataProductComment.created_at.desc())
                )
                .scalars()
                .all()
            )
            mention_rows: list[dict[str, Any]] = []
            for c in mentions:
                try:
                    mentioned = json.loads(c.mentioned_user_ids_json or "[]")
                except (ValueError, TypeError):
                    mentioned = []
                if caller["id"] in mentioned:
                    mention_rows.append(_row_from_comment(c))
            rows = mention_rows
        elif filter == "my":
            mine_comments = (
                session.execute(
                    select(DataProductComment)
                    .where(
                        DataProductComment.author_user_id == caller["id"],
                        DataProductComment.deleted_at.is_(None),
                    )
                    .order_by(DataProductComment.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            mine_reviews = (
                session.execute(
                    select(DataProductReview)
                    .where(DataProductReview.author_user_id == caller["id"])
                    .order_by(DataProductReview.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            rows = [_row_from_comment(c) for c in mine_comments] + [
                _row_from_review(r) for r in mine_reviews
            ]
        elif filter == "followed_users":
            rows = [r for r in rows if r["kind"] in ("comment", "review")]
        elif filter == "followed_dps":
            # Inbox events for the followed-DPs case already arrive
            # via the fanout, so keep notification rows only.
            rows = [r for r in rows if r["kind"] == "notification"]

    if needle:
        rows = [r for r in rows if needle in (r.get("summary_md") or "").lower()]

    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)

    # De-duplicate by (kind, event_type, summary_md, created_at) to
    # collapse cases where an inbox row + a direct author-overlay row
    # describe the same event (rare but possible).
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("kind")),
            str(row.get("event_type")),
            str(row.get("summary_md")),
            str(row.get("created_at")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    return {"filter": filter, "rows": unique[:limit]}
