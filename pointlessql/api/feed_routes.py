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

import datetime
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._feed_mute import FeedMute
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["feed"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

# Phase 81.K.4 — snooze durations expressed as relative seconds.
# Keys are the labels the UI surfaces; values are the wall-clock
# offset added to ``now()`` when the user picks one.
_SNOOZE_DURATIONS: dict[str, datetime.timedelta] = {
    "1h": datetime.timedelta(hours=1),
    "8h": datetime.timedelta(hours=8),
    "1d": datetime.timedelta(days=1),
}


class _MuteBody(BaseModel):
    """Request body for ``POST /api/feed/mute``."""

    entity_kind: str
    entity_ref: str


class _MuteAuthorBody(BaseModel):
    """Request body for ``POST /api/feed/mute-author``."""

    user_id: int


class _SnoozeBody(BaseModel):
    """Request body for ``POST /api/feed/snooze``."""

    entity_kind: str
    entity_ref: str
    duration: str


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


def _classify_notification(event_type: str) -> str:
    """Map a ``user_notifications.event_type`` to a feed render kind.

    Phase 81.K.2 — the renderer wants a coarser bucket than the dotted
    event-type string so per-kind Alpine branches stay readable.
    ``mentioned`` substrings light up the mention treatment, the rest
    map by prefix.  Unknown event types fall through to the generic
    notification card.

    Args:
        event_type: ``pointlessql.<scope>.<verb>`` event identifier.

    Returns:
        One of ``mention``, ``agent_run``, ``badge_award``, ``issue``,
        ``branch``, ``notification``.
    """
    if not event_type:
        return "notification"
    if "mentioned" in event_type or ".mention" in event_type:
        return "mention"
    if event_type.startswith("pointlessql.agent_run."):
        return "agent_run"
    if event_type.startswith("pointlessql.user.badge_"):
        return "badge_award"
    if event_type.startswith("pointlessql.issue."):
        return "issue"
    if event_type.startswith("pointlessql.branch."):
        return "branch"
    return "notification"


def _row_from_notification(
    row: UserNotification,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
) -> dict[str, Any]:
    """Normalise a ``UserNotification`` to the feed row shape.

    Phase 81.K.2 adds the coarse ``render_kind`` discriminator + actor
    display-name resolution so the Alpine renderer can branch on a
    single field instead of substring-matching ``event_type``.

    Args:
        row: The notification row.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for DP-URL fallback.
        actor_names: ``{user_id: display_name}`` cache built once
            per feed request.

    Returns:
        Feed-row dict ready for JSON serialisation.
    """
    source_url = row.source_url or _dp_url_from_id(
        fqn_map, row.source_data_product_id
    )
    render_kind = _classify_notification(row.event_type or "")
    return {
        "id": row.id,
        "kind": "notification",
        "render_kind": render_kind,
        "event_type": row.event_type,
        "summary_md": row.summary_md,
        "body_md": row.summary_md,
        "source_url": source_url,
        "data_product_id": row.source_data_product_id,
        "entity_kind": row.source_entity_kind,
        "entity_ref": row.source_entity_ref,
        "actor_user_id": row.actor_user_id,
        "actor_display_name": (
            actor_names.get(int(row.actor_user_id))
            if row.actor_user_id is not None
            else None
        ),
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def _row_from_comment(
    comment: DataProductComment,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
    target: SocialTarget | None = None,
) -> dict[str, Any]:
    """Normalise a comment to the feed row shape.

    Phase 81.K.2 carries the full ``body_md`` (Alpine truncates +
    "Show more"), ``actor_display_name``, ``comment_id``, and a
    ``render_kind`` of ``comment`` for the per-kind renderer.

    Args:
        comment: The comment row to normalise.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for the DP fallback.
        actor_names: ``{user_id: display_name}`` cache.
        target: Optional joined ``social_targets`` row.

    Returns:
        Feed-row dict (kind / event_type / summary / source_url /
        entity_kind / entity_ref / actor / timestamps).
    """
    dp_id = comment.data_product_id
    if target is not None:
        entity_kind = str(target.entity_kind)
        entity_ref = str(target.entity_ref)
        source_url = entity_registry.url_for(entity_kind, entity_ref)
    else:
        entity_kind = "dp"
        entity_ref = (
            fqn_map.get(int(dp_id)) if dp_id is not None else None
        )
        source_url = _dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "comment",
        "render_kind": "comment",
        "event_type": "pointlessql.data_product.commented",
        "summary_md": comment.body_md[:160],
        "body_md": comment.body_md,
        "comment_id": comment.id,
        "source_url": source_url,
        "data_product_id": dp_id,
        "entity_kind": entity_kind,
        "entity_ref": entity_ref,
        "actor_user_id": comment.author_user_id,
        "actor_display_name": actor_names.get(int(comment.author_user_id)),
        "created_at": comment.created_at.isoformat(),
        "read_at": None,
    }


def _row_from_review(
    review: DataProductReview,
    fqn_map: dict[int, str],
    actor_names: dict[int, str],
    target: SocialTarget | None = None,
) -> dict[str, Any]:
    """Normalise a review to the feed row shape.

    Phase 81.K.2 carries ``stars`` as a separate integer field
    (Alpine renders the actual stars row), full ``body_md``, and
    ``actor_display_name`` for the per-kind renderer.

    Args:
        review: The review row to normalise.
        fqn_map: ``{dp_id: 'cat.sch'}`` cache for the DP fallback.
        actor_names: ``{user_id: display_name}`` cache.
        target: Optional joined ``social_targets`` row.

    Returns:
        Feed-row dict with the same shape as the comment row, plus
        a top-level ``stars`` integer.
    """
    dp_id = review.data_product_id
    if target is not None:
        entity_kind = str(target.entity_kind)
        entity_ref = str(target.entity_ref)
        source_url = entity_registry.url_for(entity_kind, entity_ref)
    else:
        entity_kind = "dp"
        entity_ref = (
            fqn_map.get(int(dp_id)) if dp_id is not None else None
        )
        source_url = _dp_url_from_id(fqn_map, dp_id)
    return {
        "kind": "review",
        "render_kind": "review",
        "event_type": "pointlessql.data_product.reviewed",
        "summary_md": f"{'★' * review.stars} — {review.body_md[:120]}",
        "body_md": review.body_md,
        "stars": int(review.stars),
        "source_url": source_url,
        "data_product_id": dp_id,
        "entity_kind": entity_kind,
        "entity_ref": entity_ref,
        "actor_user_id": review.author_user_id,
        "actor_display_name": actor_names.get(int(review.author_user_id)),
        "created_at": review.created_at.isoformat(),
        "read_at": None,
    }


def _active_mute_keys(
    session: Any, user_id: int
) -> set[tuple[str, str]]:
    """Return ``{(entity_kind, entity_ref)}`` the caller has muted.

    Phase 81.K.4 — the feed handler calls this once per request and
    drops rows whose ``(entity_kind, entity_ref)`` is in the set
    before serialising.  Rows with ``muted_until`` in the past are
    ignored (the rows persist so the user's history of mute picks
    survives, but they don't filter live data).

    Args:
        session: SQLAlchemy session.
        user_id: The caller's user id.

    Returns:
        Set of ``(entity_kind, entity_ref)`` tuples currently muted.
    """
    now = datetime.datetime.now(datetime.UTC)
    rows = session.execute(
        select(FeedMute.entity_kind, FeedMute.entity_ref).where(
            FeedMute.user_id == user_id,
            or_(
                FeedMute.muted_until.is_(None),
                FeedMute.muted_until > now,
            ),
        )
    ).all()
    return {(str(k), str(r)) for k, r in rows}


def _build_actor_names(
    session: Any, rows_iter: Any
) -> dict[int, str]:
    """Resolve ``{user_id: display_name}`` for actors in a row batch.

    Phase 81.K.2 — the renderer needs actor display names to attribute
    feed items.  Building the map once per request avoids one query
    per row.  Pass any iterable of ``actor_user_id``-bearing objects
    (UserNotification, DataProductComment, DataProductReview); the
    function de-duplicates and returns only the ids it found.

    Args:
        session: SQLAlchemy session.
        rows_iter: Iterable of ORM rows carrying ``actor_user_id`` or
            ``author_user_id``.

    Returns:
        Dict mapping user-id to display-name.  Missing ids are simply
        absent; callers ``.get`` with a fallback.
    """
    ids: set[int] = set()
    for r in rows_iter:
        for attr in ("actor_user_id", "author_user_id"):
            v = getattr(r, attr, None)
            if v is not None:
                ids.add(int(v))
    if not ids:
        return {}
    pairs = session.execute(
        select(User.id, User.display_name).where(User.id.in_(ids))
    ).all()
    return {int(uid): str(name) for uid, name in pairs}


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
    kind: str | None = None,
) -> dict[str, Any]:
    """Return the caller's merged feed.

    Phase 77.9 — the feed now lists comments + reviews across every
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
            # Phase 77.9 — JOIN the polymorphic anchor so cross-kind
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

        # Phase 81.K.2 — bulk-resolve actor display names so every
        # feed row carries an attribution line.  One SELECT for all
        # actor + author user-ids surfaced above.
        actor_names = _build_actor_names(
            session,
            list(inbox)
            + [c for c, _ in comments_rows]
            + [r for r, _ in reviews_rows],
        )

        rows.extend(
            _row_from_notification(n, fqn_map, actor_names) for n in inbox
        )
        rows.extend(
            _row_from_comment(c, fqn_map, actor_names, t)
            for c, t in comments_rows
        )
        rows.extend(
            _row_from_review(r, fqn_map, actor_names, t)
            for r, t in reviews_rows
        )

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
            mention_actor_names = _build_actor_names(session, mentions)
            mention_rows: list[dict[str, Any]] = []
            for c in mentions:
                try:
                    mentioned = json.loads(c.mentioned_user_ids_json or "[]")
                except (ValueError, TypeError):
                    mentioned = []
                if caller["id"] in mentioned:
                    mention_rows.append(
                        _row_from_comment(c, fqn_map, mention_actor_names, None)
                    )
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
            my_actor_names = _build_actor_names(
                session, list(mine_comments) + list(mine_reviews)
            )
            rows = [
                _row_from_comment(c, fqn_map, my_actor_names, None)
                for c in mine_comments
            ] + [
                _row_from_review(r, fqn_map, my_actor_names, None)
                for r in mine_reviews
            ]
        elif filter == "followed_users":
            rows = [r for r in rows if r["kind"] in ("comment", "review")]
        elif filter == "followed_dps":
            # Inbox events for the followed-DPs case already arrive
            # via the fanout, so keep notification rows only.
            rows = [r for r in rows if r["kind"] == "notification"]

    if needle:
        rows = [r for r in rows if needle in (r.get("summary_md") or "").lower()]

    # Phase 81.K.2 — kind-filter accepts a comma-separated list of
    # entity-kind values; rows pass when any selected kind matches.
    # A single value keeps the Phase 77.9 single-kind behaviour.
    if kind:
        wanted_kinds = {k.strip() for k in kind.split(",") if k.strip()}
        if wanted_kinds:
            rows = [r for r in rows if r.get("entity_kind") in wanted_kinds]

    # Phase 81.K.4 — drop rows muted by the caller.  Muted threads
    # are identified by ``(entity_kind, entity_ref)``; muted authors
    # are stored as ``(entity_kind='user', entity_ref=<user_id>)``
    # so the same set covers both axes in one membership test.
    with factory() as session:
        mute_keys = _active_mute_keys(session, caller["id"])
    if mute_keys:
        rows = [
            r for r in rows
            if (str(r.get("entity_kind")), str(r.get("entity_ref")))
            not in mute_keys
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
# Phase 81.K.4 — item-level action endpoints.
#
# All five share the same shape: take the caller from the session,
# mutate the appropriate row, return ``{"ok": true}``.  Errors raise
# 4xx so the Alpine layer can surface them via toast.
# ---------------------------------------------------------------


@router.post("/api/notifications/mark-all-read")
async def mark_all_read(request: Request) -> dict[str, Any]:
    """Mark every unread notification for the caller as read.

    Phase 81.K.4 — the feed's top-level "Mark all read" button posts
    here; the per-item endpoint covers the granular case.  Returns
    the count touched so the UI can confirm.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"ok": true, "count": N}`` where N is the number of rows
        flipped from unread to read.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        result = session.execute(
            update(UserNotification)
            .where(
                UserNotification.recipient_user_id == caller["id"],
                UserNotification.workspace_id == workspace_id,
                UserNotification.read_at.is_(None),
            )
            .values(read_at=now)
        )
        session.commit()
        # rowcount is dialect-dependent; cast to int defensively.
        count = int(result.rowcount or 0)
    return {"ok": True, "count": count}


@router.post("/api/notifications/{notification_id}/read")
async def toggle_notification_read(
    request: Request, notification_id: int
) -> dict[str, Any]:
    """Toggle the ``read_at`` flag on a single notification.

    Phase 81.K.4 — the item-action menu's "Mark as read / unread"
    entry posts here.  We only allow the caller to flip rows
    addressed to themselves.

    Args:
        request: Incoming FastAPI request.
        notification_id: Primary key of the notification.

    Returns:
        ``{"ok": true, "read": bool}`` with the new state.

    Raises:
        HTTPException: 404 if the row doesn't belong to the caller.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.id == notification_id,
                UserNotification.recipient_user_id == caller["id"],
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        now = datetime.datetime.now(datetime.UTC)
        if row.read_at is None:
            row.read_at = now
            new_state = True
        else:
            row.read_at = None
            new_state = False
        session.commit()
    return {"ok": True, "read": new_state}


def _upsert_mute(
    session: Any,
    user_id: int,
    entity_kind: str,
    entity_ref: str,
    muted_until: datetime.datetime | None,
) -> None:
    """Insert or update a single mute row.

    The unique index ``uq_feed_mutes_per_target`` guarantees one row
    per ``(user_id, entity_kind, entity_ref)`` — re-muting updates
    the ``muted_until`` instead of duplicating.

    Args:
        session: SQLAlchemy session.
        user_id: Caller's user-id.
        entity_kind: Discriminator.
        entity_ref: Entity reference.
        muted_until: Optional snooze deadline.
    """
    existing = session.execute(
        select(FeedMute).where(
            FeedMute.user_id == user_id,
            FeedMute.entity_kind == entity_kind,
            FeedMute.entity_ref == entity_ref,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            FeedMute(
                user_id=user_id,
                entity_kind=entity_kind,
                entity_ref=entity_ref,
                muted_until=muted_until,
            )
        )
    else:
        existing.muted_until = muted_until
    session.commit()


@router.post("/api/feed/mute")
async def mute_thread(request: Request, body: _MuteBody) -> dict[str, Any]:
    """Mute a thread (entity) for the caller's feed indefinitely.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref}`` JSON payload.

    Returns:
        ``{"ok": true}`` on success.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            body.entity_kind,
            body.entity_ref,
            muted_until=None,
        )
    return {"ok": True}


@router.post("/api/feed/mute-author")
async def mute_author(
    request: Request, body: _MuteAuthorBody
) -> dict[str, Any]:
    """Mute every feed item authored by *user_id* for the caller.

    Stored as a ``feed_mutes`` row with ``entity_kind='user'`` so the
    feed handler's single mute-set membership check covers both
    threads and authors.

    Args:
        request: Incoming FastAPI request.
        body: ``{user_id}`` JSON payload.

    Returns:
        ``{"ok": true}`` on success.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            "user",
            str(body.user_id),
            muted_until=None,
        )
    return {"ok": True}


@router.post("/api/feed/snooze")
async def snooze_thread(
    request: Request, body: _SnoozeBody
) -> dict[str, Any]:
    """Snooze a thread for one of the canonical durations.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref, duration}`` JSON payload.
            ``duration`` must be one of ``1h`` / ``8h`` / ``1d``.

    Returns:
        ``{"ok": true, "muted_until": iso8601}`` with the deadline.

    Raises:
        HTTPException: 400 if ``duration`` is unknown.
    """
    require_user(request)
    caller = get_user(request)
    delta = _SNOOZE_DURATIONS.get(body.duration)
    if delta is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown duration {body.duration!r}; "
                f"expected one of {sorted(_SNOOZE_DURATIONS)}"
            ),
        )
    muted_until = datetime.datetime.now(datetime.UTC) + delta
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            body.entity_kind,
            body.entity_ref,
            muted_until=muted_until,
        )
    return {"ok": True, "muted_until": muted_until.isoformat()}


@router.post("/api/feed/unmute")
async def unmute(request: Request, body: _MuteBody) -> dict[str, Any]:
    """Remove a mute / snooze entry for the caller.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref}`` JSON payload.

    Returns:
        ``{"ok": true, "removed": bool}`` — ``removed`` is ``False``
        when no matching row existed (idempotent unmute).
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        existing = session.execute(
            select(FeedMute).where(
                FeedMute.user_id == caller["id"],
                FeedMute.entity_kind == body.entity_kind,
                FeedMute.entity_ref == body.entity_ref,
            )
        ).scalar_one_or_none()
        if existing is None:
            return {"ok": True, "removed": False}
        session.delete(existing)
        session.commit()
    return {"ok": True, "removed": True}


# ---------------------------------------------------------------
# Phase 81.K.5 — right-column endpoints.
#
# Two read-only feeds drive the discovery panel:
# ``GET /api/feed/trending`` and ``GET /api/feed/people``.  Both
# scope to the caller's workspace; both surface only entities /
# users that have actually been active in the relevant window.
# ---------------------------------------------------------------

_TRENDING_WINDOW = datetime.timedelta(hours=24)
_PEOPLE_WINDOW = datetime.timedelta(days=7)


@router.get("/api/feed/trending")
async def get_trending(
    request: Request, limit: int = 5
) -> dict[str, Any]:
    """Top-N entities by activity-count in the caller's workspace.

    Phase 81.K.5 — drives the "Trending today" card on the feed's
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
async def get_people_to_follow(
    request: Request, limit: int = 5
) -> dict[str, Any]:
    """Top contributors the caller doesn't follow yet.

    Phase 81.K.5 — drives the "People to follow" card.  Looks at
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
                (uid, total) for uid, total in totals.items()
                if uid != caller["id"] and uid not in followed
            ),
            key=lambda x: x[1],
            reverse=True,
        )[:cap]
        if not candidates:
            return {"rows": []}
        ids = [uid for uid, _ in candidates]
        names = dict(
            session.execute(
                select(User.id, User.display_name).where(User.id.in_(ids))
            ).all()
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
