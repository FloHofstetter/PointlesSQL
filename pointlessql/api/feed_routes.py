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
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["feed"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _dp_url_from_id(fqn_map: dict[int, str], dp_id: int | None) -> str:
    """Build the DP detail URL from an id via the entity registry.

    Phase 77.0.I — the URL is built through
    :func:`entity_registry.url_for` so the same lookup table
    powers every future kind (table / model / branch / …).
    ``fqn_map`` is the per-request ``{dp_id: 'cat.sch'}`` cache
    pre-fetched by the feed handler.  Falls back to the legacy
    fragment-anchor format when the id is unknown (e.g.
    historic row whose DP was deleted) so the link is at least
    parseable.
    """
    fqn = fqn_map.get(int(dp_id)) if dp_id is not None else None
    if fqn is None:
        return f"/data-products/#{dp_id}"
    return entity_registry.url_for("dp", fqn)


def _row_from_notification(
    row: UserNotification, fqn_map: dict[int, str]
) -> dict[str, Any]:
    """Normalise a ``UserNotification`` to the feed row shape."""
    # Phase 77.0.D / 77.0.I — polymorphic source_url:
    # rows fanned out via fanout_event already carry a
    # source_url that the dispatcher built, so prefer that.
    source_url = row.source_url or _dp_url_from_id(
        fqn_map, row.source_data_product_id
    )
    return {
        "kind": "notification",
        "event_type": row.event_type,
        "summary_md": row.summary_md,
        "source_url": source_url,
        "data_product_id": row.source_data_product_id,
        "entity_kind": row.source_entity_kind,
        "entity_ref": row.source_entity_ref,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def _row_from_comment(
    comment: DataProductComment, fqn_map: dict[int, str]
) -> dict[str, Any]:
    """Normalise a comment to the feed row shape."""
    return {
        "kind": "comment",
        "event_type": "pointlessql.data_product.commented",
        "summary_md": comment.body_md[:160],
        "source_url": _dp_url_from_id(fqn_map, comment.data_product_id),
        "data_product_id": comment.data_product_id,
        "entity_kind": "dp",
        "entity_ref": fqn_map.get(int(comment.data_product_id)),
        "actor_user_id": comment.author_user_id,
        "created_at": comment.created_at.isoformat(),
        "read_at": None,
    }


def _row_from_review(
    review: DataProductReview, fqn_map: dict[int, str]
) -> dict[str, Any]:
    """Normalise a review to the feed row shape."""
    return {
        "kind": "review",
        "event_type": "pointlessql.data_product.reviewed",
        "summary_md": f"{'★' * review.stars} — {review.body_md[:120]}",
        "source_url": _dp_url_from_id(fqn_map, review.data_product_id),
        "data_product_id": review.data_product_id,
        "entity_kind": "dp",
        "entity_ref": fqn_map.get(int(review.data_product_id)),
        "actor_user_id": review.author_user_id,
        "created_at": review.created_at.isoformat(),
        "read_at": None,
    }


def _build_fqn_map(session: Any, workspace_id: int) -> dict[int, str]:
    """Cache ``{dp_id: 'cat.sch'}`` for every DP in the workspace.

    The feed handler pre-fetches this once per request so the row
    builders can synthesise URLs via the entity registry without
    re-issuing one SELECT per row.
    """
    rows = session.execute(
        select(
            DataProduct.id, DataProduct.catalog_name, DataProduct.schema_name
        ).where(DataProduct.workspace_id == workspace_id)
    ).all()
    return {int(dp_id): f"{cat}.{sch}" for dp_id, cat, sch in rows}


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
        # Phase 77.0.I — per-request DP-FQN cache feeds the
        # registry-driven URL builder so every feed row carries
        # the same shape ``social_target.entity_ref`` rows use.
        fqn_map = _build_fqn_map(session, workspace_id)

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
        rows.extend(_row_from_notification(n, fqn_map) for n in inbox)

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
            rows.extend(_row_from_comment(c, fqn_map) for c in comments)

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
            rows.extend(_row_from_review(r, fqn_map) for r in reviews)

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
                    mention_rows.append(_row_from_comment(c, fqn_map))
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
            rows = [
                _row_from_comment(c, fqn_map) for c in mine_comments
            ] + [_row_from_review(r, fqn_map) for r in mine_reviews]
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
