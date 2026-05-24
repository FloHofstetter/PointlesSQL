"""Read-only feed endpoints: merged inbox, trending, people-to-follow.

* ``GET /api/feed`` — the canonical merged feed used by the activity
  pane.  Combines ``user_notifications`` rows (the fan-out target for
  every reactive social event) with comments + reviews authored by
  users the caller follows, dedupes, mute-filters, and returns the
  Alpine-renderable shape.
* ``GET /api/feed/trending`` — top-N entities by 24 h activity count.
* ``GET /api/feed/people`` — top contributors the caller does not
  already follow, 7 d window.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.api.feed_routes._serializers import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    active_mute_keys,
    build_actor_names,
    build_fqn_map,
    row_from_comment,
    row_from_notification,
    row_from_review,
)
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["feed"])

_TRENDING_WINDOW = datetime.timedelta(hours=24)
_PEOPLE_WINDOW = datetime.timedelta(days=7)


@router.get("/api/feed")
async def get_feed(
    request: Request,
    filter: str = "all",  # noqa: A002 — query param shadows builtin intentionally
    limit: int = DEFAULT_LIMIT,
    q: str = "",
    kind: str | None = None,
) -> dict[str, Any]:
    """Return the caller's merged feed.

    the feed now lists comments + reviews across every
    polymorphic entity kind (table / model / branch / run / etc.),
    not just data products.  The new optional ``kind`` query
    parameter narrows the result set to one ``entity_kind`` value;
    legacy ``kind=dp`` keeps the historical DP-only view available.
    Each row's ``source_url`` is built through
    :func:`entity_registry.url_for` so the link lands on the right
    detail page regardless of kind.

    Args:
        request: Incoming FastAPI request.
        filter: One of ``all`` (default), ``mentions``,
            ``followed_users``, ``followed_dps``, ``my``.
            Unknown values fall back to ``all``.
        limit: Result cap; clamped to ``[1, 200]``.
        q: Optional substring match on the row summary.  Case-
            insensitive; an empty value disables filtering.
        kind: Optional ``entity_kind`` narrow — e.g. ``table`` keeps
            only table comments/reviews/notifications.  ``None``
            disables the filter.

    Returns:
        ``{"filter": str, "kind": str | None, "rows": [...]}``
        sorted by ``created_at`` descending.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    limit = max(1, min(MAX_LIMIT, int(limit)))
    needle = q.strip().lower()

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        # per-request DP-FQN cache feeds the
        # registry-driven URL builder so every feed row carries
        # the same shape ``social_target.entity_ref`` rows use.
        fqn_map = build_fqn_map(session, workspace_id)

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

        # Followed-users overlay (comments + reviews).
        followed_user_ids: list[int] = [
            int(uid)
            for (uid,) in session.execute(
                select(UserFollow.followed_user_id).where(
                    UserFollow.follower_user_id == caller["id"]
                )
            ).all()
        ]
        comments_rows: list[Any] = []
        reviews_rows: list[Any] = []
        if followed_user_ids:
            # JOIN the polymorphic anchor so cross-kind
            # comments + reviews flow into the feed with the right
            # entity_kind/entity_ref + source_url.
            comments_rows = session.execute(
                select(DataProductComment, SocialTarget)
                .outerjoin(
                    SocialTarget,
                    DataProductComment.social_target_id == SocialTarget.id,
                )
                .where(
                    DataProductComment.author_user_id.in_(followed_user_ids),
                    DataProductComment.workspace_id == workspace_id,
                    DataProductComment.deleted_at.is_(None),
                )
                .order_by(DataProductComment.created_at.desc())
                .limit(limit)
            ).all()
            reviews_rows = session.execute(
                select(DataProductReview, SocialTarget)
                .outerjoin(
                    SocialTarget,
                    DataProductReview.social_target_id == SocialTarget.id,
                )
                .where(
                    DataProductReview.author_user_id.in_(followed_user_ids),
                    DataProductReview.workspace_id == workspace_id,
                )
                .order_by(DataProductReview.created_at.desc())
                .limit(limit)
            ).all()

        # bulk-resolve actor display names so every
        # feed row carries an attribution line.  One SELECT for all
        # actor + author user-ids surfaced above.
        actor_names = build_actor_names(
            session,
            list(inbox) + [c for c, _ in comments_rows] + [r for r, _ in reviews_rows],
        )

        rows.extend(row_from_notification(n, fqn_map, actor_names) for n in inbox)
        rows.extend(row_from_comment(c, fqn_map, actor_names, t) for c, t in comments_rows)
        rows.extend(row_from_review(r, fqn_map, actor_names, t) for r, t in reviews_rows)

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
            mention_actor_names = build_actor_names(session, mentions)
            mention_rows: list[dict[str, Any]] = []
            for c in mentions:
                try:
                    mentioned = json.loads(c.mentioned_user_ids_json or "[]")
                except ValueError, TypeError:
                    mentioned = []
                if caller["id"] in mentioned:
                    mention_rows.append(row_from_comment(c, fqn_map, mention_actor_names, None))
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
            my_actor_names = build_actor_names(session, list(mine_comments) + list(mine_reviews))
            rows = [row_from_comment(c, fqn_map, my_actor_names, None) for c in mine_comments] + [
                row_from_review(r, fqn_map, my_actor_names, None) for r in mine_reviews
            ]
        elif filter == "followed_users":
            rows = [r for r in rows if r["kind"] in ("comment", "review")]
        elif filter == "followed_dps":
            # Inbox events for the followed-DPs case already arrive
            # via the fanout, so keep notification rows only.
            rows = [r for r in rows if r["kind"] == "notification"]

    if needle:
        rows = [r for r in rows if needle in (r.get("summary_md") or "").lower()]

    # kind-filter accepts a comma-separated list of
    # entity-kind values; rows pass when any selected kind matches.
    # A single value keeps the single-kind behaviour.
    if kind:
        wanted_kinds = {k.strip() for k in kind.split(",") if k.strip()}
        if wanted_kinds:
            rows = [r for r in rows if r.get("entity_kind") in wanted_kinds]

    # drop rows muted by the caller.  Muted threads
    # are identified by ``(entity_kind, entity_ref)``; muted authors
    # are stored as ``(entity_kind='user', entity_ref=<user_id>)``
    # so the same set covers both axes in one membership test.
    with factory() as session:
        mute_keys = active_mute_keys(session, caller["id"])
    if mute_keys:
        rows = [
            r
            for r in rows
            if (str(r.get("entity_kind")), str(r.get("entity_ref"))) not in mute_keys
            and ("user", str(r.get("actor_user_id"))) not in mute_keys
        ]

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

    return {"filter": filter, "kind": kind, "rows": unique[:limit]}


# ---------------------------------------------------------------
# right-column endpoints.
#
# Two read-only feeds drive the discovery panel:
# ``GET /api/feed/trending`` and ``GET /api/feed/people``.  Both
# scope to the caller's workspace; both surface only entities /
# users that have actually been active in the relevant window.
# ---------------------------------------------------------------


@router.get("/api/feed/trending")
async def get_trending(request: Request, limit: int = 5) -> dict[str, Any]:
    """Top-N entities by activity-count in the caller's workspace.

    drives the "Trending today" card on the feed's
    right column.  Aggregates ``user_notifications`` group-by
    ``(source_entity_kind, source_entity_ref)`` over the last 24 h,
    count desc.

    Args:
        request: Incoming FastAPI request.
        limit: Result cap; clamped to ``[1, 20]``.  Defaults to 5
            (one card-row each).

    Returns:
        ``{"rows": [{"entity_kind", "entity_ref", "label",
        "source_url", "count"}, ...]}`` sorted count desc.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    cap = max(1, min(20, int(limit)))
    factory = request.app.state.session_factory
    cutoff = datetime.datetime.now(datetime.UTC) - _TRENDING_WINDOW
    with factory() as session:
        rows = session.execute(
            select(
                UserNotification.source_entity_kind,
                UserNotification.source_entity_ref,
                func.count().label("c"),
            )
            .where(
                UserNotification.workspace_id == workspace_id,
                UserNotification.created_at >= cutoff,
                UserNotification.source_entity_kind.is_not(None),
                UserNotification.source_entity_ref.is_not(None),
            )
            .group_by(
                UserNotification.source_entity_kind,
                UserNotification.source_entity_ref,
            )
            .order_by(func.count().desc())
            .limit(cap)
        ).all()
    out: list[dict[str, Any]] = []
    for kind, ref, count in rows:
        if not kind or not ref:
            continue
        out.append(
            {
                "entity_kind": str(kind),
                "entity_ref": str(ref),
                "label": str(ref),  # ref already reads as the FQN
                "source_url": entity_registry.url_for(str(kind), str(ref)),
                "count": int(count),
            }
        )
    return {"rows": out}


@router.get("/api/feed/people")
async def get_people_to_follow(request: Request, limit: int = 5) -> dict[str, Any]:
    """Top contributors the caller doesn't follow yet.

    drives the "People to follow" card.  Looks at
    the last 7 days of comments + reviews, picks the most active
    authors that aren't already in the caller's ``user_follows``
    set, and returns ``{id, display_name, recent_event_count}``.

    Args:
        request: Incoming FastAPI request.
        limit: Result cap; clamped to ``[1, 20]``.  Defaults to 5.

    Returns:
        ``{"rows": [...]}`` sorted by recent-event count desc.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    cap = max(1, min(20, int(limit)))
    factory = request.app.state.session_factory
    cutoff = datetime.datetime.now(datetime.UTC) - _PEOPLE_WINDOW
    with factory() as session:
        # Already-followed user ids.
        followed: set[int] = {
            int(uid)
            for (uid,) in session.execute(
                select(UserFollow.followed_user_id).where(
                    UserFollow.follower_user_id == caller["id"]
                )
            ).all()
        }
        # Comment + review activity authored in window.  Counts both
        # tables and sums client-side to keep the SQL portable across
        # SQLite + Postgres.
        comment_counts = session.execute(
            select(
                DataProductComment.author_user_id,
                func.count().label("c"),
            )
            .where(
                DataProductComment.workspace_id == workspace_id,
                DataProductComment.created_at >= cutoff,
                DataProductComment.deleted_at.is_(None),
            )
            .group_by(DataProductComment.author_user_id)
        ).all()
        review_counts = session.execute(
            select(
                DataProductReview.author_user_id,
                func.count().label("c"),
            )
            .where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.created_at >= cutoff,
            )
            .group_by(DataProductReview.author_user_id)
        ).all()
        totals: dict[int, int] = {}
        for uid, c in comment_counts:
            totals[int(uid)] = totals.get(int(uid), 0) + int(c)
        for uid, c in review_counts:
            totals[int(uid)] = totals.get(int(uid), 0) + int(c)
        # Drop caller + already-followed.
        candidates = sorted(
            (
                (uid, total)
                for uid, total in totals.items()
                if uid != caller["id"] and uid not in followed
            ),
            key=lambda x: x[1],
            reverse=True,
        )[:cap]
        if not candidates:
            return {"rows": []}
        ids = [uid for uid, _ in candidates]
        names = dict(
            session.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
        )
    return {
        "rows": [
            {
                "id": int(uid),
                "display_name": str(names.get(uid, f"user-{uid}")),
                "recent_event_count": int(total),
            }
            for uid, total in candidates
        ]
    }
