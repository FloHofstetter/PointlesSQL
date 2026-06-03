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
from sqlalchemy import and_, func, or_, select

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
    row_from_pending_run,
    row_from_review,
    row_from_signal,
)
from pointlessql.models.actionable_signals import STATUS_OPEN, ActionableSignal
from pointlessql.models.agent._runs import STATUS_NEEDS_APPROVAL, AgentRun
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.notifications import FeedReadMarker, UserNotification
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.notifications.categories import (
    ATTENTION_ACT,
    ATTENTION_FOR_YOU,
    count_by_category,
)
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["feed"])

_TRENDING_WINDOW = datetime.timedelta(hours=24)
_PEOPLE_WINDOW = datetime.timedelta(days=7)


def _parse_row_dt(value: object) -> datetime.datetime | None:
    """Parse a serialized row's ``created_at`` back to a datetime.

    Row timestamps are ISO-8601 strings produced by ``.isoformat()`` on
    timezone-aware UTC datetimes.  Returns ``None`` for empty / malformed
    values (e.g. a pending run with no ``started_at``) so the caller can
    treat the row as not-new rather than crash on the seen-cursor
    comparison.

    Args:
        value: The row's ``created_at`` field.

    Returns:
        A timezone-aware datetime, or ``None`` when unparseable.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed
# Entity kinds whose ``entity_ref`` is an internal id with no standalone
# display value — excluded from the Trending rail.
_TRENDING_SKIP_KINDS = frozenset({"user", "review", "badge"})


@router.get("/api/feed")
async def get_feed(
    request: Request,
    filter: str = "all",  # noqa: A002 — query param shadows builtin intentionally
    limit: int = DEFAULT_LIMIT,
    q: str = "",
    kind: str | None = None,
    category: str | None = None,
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
        category: Optional coarse-lane narrow — one of ``approval``,
            ``health``, ``social``, ``pipeline``, ``governance``.
            ``None`` or ``all`` returns every lane.  The
            ``category_counts`` in the response are computed *before*
            this slice so the chip badges stay stable when a lane is
            selected.

    Returns:
        ``{"filter", "kind", "category", "rows", "category_counts"}``
        with rows sorted by ``created_at`` descending.
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

        # One grouped SELECT for the reply count under every surfaced
        # comment, so each card can show "View N replies" without a
        # per-row query.
        reply_counts: dict[int, int] = {}
        comment_ids = [int(c.id) for c, _ in comments_rows]
        if comment_ids:
            reply_counts = {
                int(pid): int(n)
                for pid, n in session.execute(
                    select(DataProductComment.parent_comment_id, func.count())
                    .where(
                        DataProductComment.parent_comment_id.in_(comment_ids),
                        DataProductComment.workspace_id == workspace_id,
                        DataProductComment.deleted_at.is_(None),
                    )
                    .group_by(DataProductComment.parent_comment_id)
                ).all()
                if pid is not None
            }

        rows.extend(row_from_notification(n, fqn_map, actor_names) for n in inbox)
        rows.extend(
            row_from_comment(c, fqn_map, actor_names, t, reply_counts.get(int(c.id), 0))
            for c, t in comments_rows
        )
        rows.extend(row_from_review(r, fqn_map, actor_names, t) for r, t in reviews_rows)

        # Action-required lane (live): agent runs in ``needs_approval``
        # are read straight from the source table — never stored as a
        # notification — so the inline Approve / Deny card always
        # reflects the run's current state.  Admin-gated: approving is
        # admin-only, so only admins see the actionable cards.
        if caller.get("is_admin"):
            pending_runs = (
                session.execute(
                    select(AgentRun)
                    .where(
                        AgentRun.status == STATUS_NEEDS_APPROVAL,
                        AgentRun.workspace_id == workspace_id,
                    )
                    .order_by(AgentRun.started_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            # Resolve each run's principal email to a display name + id in
            # one round-trip so the approval card reads as a person, not a
            # raw email, and the avatar gets a stable per-user colour.
            principal_emails = {r.principal for r in pending_runs if r.principal}
            principals: dict[str, tuple[int, str]] = {}
            if principal_emails:
                principals = {
                    str(email): (int(uid), str(name))
                    for uid, email, name in session.execute(
                        select(User.id, User.email, User.display_name).where(
                            User.email.in_(principal_emails)
                        )
                    ).all()
                }
            rows.extend(row_from_pending_run(r, principals) for r in pending_runs)

            # Data-health / pipeline lane (live): open actionable
            # signals are read straight from the ledger, so a card
            # disappears the moment the underlying problem resolves.
            # Admin-gated like approvals — admins triage data health.
            open_signals = (
                session.execute(
                    select(ActionableSignal)
                    .where(
                        ActionableSignal.status == STATUS_OPEN,
                        ActionableSignal.workspace_id == workspace_id,
                    )
                    .order_by(ActionableSignal.opened_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            rows.extend(row_from_signal(s) for s in open_signals)

        # Attention-tier counts power the "needs you" badge + zone
        # header.  They are counted independently of the row slice so a
        # capped fetch never under-reports what is waiting.  The ``act``
        # work (approvals + open signals) is admin-gated like the cards;
        # the ``for_you`` count is per-recipient and covers every caller.
        # Legacy rows written before the ``attention`` column existed are
        # treated as ``for_you`` only when their event type is a mention,
        # mirroring :func:`attention_for_event`.
        needs_action_count = 0
        if caller.get("is_admin"):
            pending_count = session.execute(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.status == STATUS_NEEDS_APPROVAL,
                    AgentRun.workspace_id == workspace_id,
                )
            ).scalar()
            signal_count = session.execute(
                select(func.count())
                .select_from(ActionableSignal)
                .where(
                    ActionableSignal.status == STATUS_OPEN,
                    ActionableSignal.workspace_id == workspace_id,
                )
            ).scalar()
            needs_action_count = int(pending_count or 0) + int(signal_count or 0)
        # Seen-cursor — the per-(user, workspace) high-water mark that
        # splits "new" ambient rows from already-seen history.  ``None``
        # (no marker yet) means the reader has seen nothing, so every
        # row reads as new until they catch up.
        seen_at = session.execute(
            select(FeedReadMarker.seen_at).where(
                FeedReadMarker.user_id == caller["id"],
                FeedReadMarker.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        # SQLite drops the offset on a ``DateTime(timezone=True)`` column,
        # so a cursor read back here is naive; normalise to UTC before any
        # comparison against the (UTC-aware) parsed row timestamps.
        if seen_at is not None and seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=datetime.UTC)
        unread_for_you_count = int(
            session.execute(
                select(func.count())
                .select_from(UserNotification)
                .where(
                    UserNotification.recipient_user_id == caller["id"],
                    UserNotification.workspace_id == workspace_id,
                    UserNotification.read_at.is_(None),
                    or_(
                        UserNotification.attention == ATTENTION_FOR_YOU,
                        and_(
                            UserNotification.attention.is_(None),
                            UserNotification.event_type.like("%mention%"),
                        ),
                    ),
                )
            ).scalar()
            or 0
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

    # Chip counts are tallied across every lane *before* the category
    # slice so the badges don't collapse to the selected lane.
    category_counts = count_by_category(unique)

    # Category slice — coarse lane narrow over the stamped ``category``
    # field.  ``all`` / unset returns every lane.
    if category and category != "all":
        unique = [r for r in unique if r.get("category") == category]

    result_rows = unique[:limit]

    # Stamp each row "new" relative to the seen-cursor, and tally how
    # many *stream* rows are still unseen — i.e. rows that flow below the
    # caught-up divider, not the act / unread-for-you rows the client
    # pins into the "needs you" zone.  ``caught_up`` is the composite
    # "nothing waiting + nothing unseen" state that drives the
    # celebratory end-of-feed marker.
    unseen_count = 0
    for row in result_rows:
        row_dt = _parse_row_dt(row.get("created_at"))
        is_new = seen_at is None or (row_dt is not None and row_dt > seen_at)
        row["is_new"] = is_new
        in_zone = row.get("attention") == ATTENTION_ACT or (
            row.get("attention") == ATTENTION_FOR_YOU and not row.get("read_at")
        )
        if is_new and not in_zone:
            unseen_count += 1
    caught_up = needs_action_count == 0 and unread_for_you_count == 0 and unseen_count == 0

    return {
        "filter": filter,
        "kind": kind,
        "category": category,
        "rows": result_rows,
        "category_counts": category_counts,
        "needs_action_count": needs_action_count,
        "unread_for_you_count": unread_for_you_count,
        "unseen_count": unseen_count,
        "caught_up": caught_up,
        "seen_at": seen_at.isoformat() if seen_at else None,
    }


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
        # Internal-id kinds (a user PK, an agent-review id) carry no
        # human-readable label on their own and don't belong in a
        # "trending entities" list — skip them rather than surface a bare
        # "1" / "w23" to the rail.
        if str(kind) in _TRENDING_SKIP_KINDS:
            continue
        # Run refs are opaque UUIDs — show a short handle instead of the
        # full 36-char id; every other kind's ref already reads as an FQN.
        label = f"run {str(ref)[:8]}" if str(kind) == "run" else str(ref)
        out.append(
            {
                "entity_kind": str(kind),
                "entity_ref": str(ref),
                "label": label,
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
