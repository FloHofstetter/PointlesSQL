"""Data-fetch helpers for the feed endpoints.

Each function isolates one ``session.execute(...)`` block that
:func:`pointlessql.api.feed_routes.feed.get_feed` (and the trending /
people rails) previously inlined, so the route bodies read as
orchestration and every query is independently testable.  The logic is
moved verbatim — these helpers introduce no behaviour change; row→dict
shaping still lives in :mod:`pointlessql.api.feed_routes._serializers`.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import and_, func, or_, select

from pointlessql.api.feed_routes._serializers import (
    build_actor_names,
    row_from_comment,
    row_from_review,
)
from pointlessql.models.actionable_signals import STATUS_OPEN, ActionableSignal
from pointlessql.models.agent._runs import STATUS_NEEDS_APPROVAL, AgentRun
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.notifications import FeedReadMarker, UserNotification
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.notifications.categories import ATTENTION_FOR_YOU


def fetch_inbox(
    session: Any, *, caller_id: int, workspace_id: int, limit: int
) -> list[UserNotification]:
    """Return the caller's inbox notifications, newest first (``limit * 2`` cap).

    Args:
        session: SQLAlchemy session.
        caller_id: Recipient user id.
        workspace_id: Active workspace.
        limit: Row cap; the over-fetch (``limit * 2``) leaves headroom for
            the post-merge filter/dedupe to trim.

    Returns:
        The matching :class:`UserNotification` rows.
    """
    return list(
        session.execute(
            select(UserNotification)
            .where(
                UserNotification.recipient_user_id == caller_id,
                UserNotification.workspace_id == workspace_id,
            )
            .order_by(UserNotification.created_at.desc())
            .limit(limit * 2)
        )
        .scalars()
        .all()
    )


def fetch_followed_user_ids(session: Any, *, caller_id: int) -> list[int]:
    """Return the ids of the users the caller follows.

    Args:
        session: SQLAlchemy session.
        caller_id: Follower user id.

    Returns:
        Followed user ids.
    """
    return [
        int(uid)
        for (uid,) in session.execute(
            select(UserFollow.followed_user_id).where(UserFollow.follower_user_id == caller_id)
        ).all()
    ]


def fetch_followed_overlay(
    session: Any, *, followed_user_ids: list[int], workspace_id: int, limit: int
) -> tuple[list[Any], list[Any]]:
    """Return comments + reviews authored by followed users (with anchors).

    Each row is joined to its polymorphic :class:`SocialTarget` so the feed
    row carries the right entity kind / ref / source URL.

    Args:
        session: SQLAlchemy session.
        followed_user_ids: Users whose activity to surface.
        workspace_id: Active workspace.
        limit: Per-table row cap.

    Returns:
        ``(comments_rows, reviews_rows)`` — each a list of
        ``(model, SocialTarget | None)`` pairs; both empty when nobody is
        followed.
    """
    if not followed_user_ids:
        return [], []
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
    return comments_rows, reviews_rows


def fetch_reply_counts(
    session: Any, *, comment_ids: list[int], workspace_id: int
) -> dict[int, int]:
    """Return ``parent_comment_id → reply count`` for the surfaced comments.

    Args:
        session: SQLAlchemy session.
        comment_ids: Parent comment ids to count replies for.
        workspace_id: Active workspace.

    Returns:
        Reply counts keyed by parent comment id; empty when no ids given.
    """
    if not comment_ids:
        return {}
    return {
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


def fetch_pending_runs(session: Any, *, workspace_id: int, limit: int) -> list[AgentRun]:
    """Return agent runs awaiting approval, newest first.

    Args:
        session: SQLAlchemy session.
        workspace_id: Active workspace.
        limit: Row cap.

    Returns:
        The :class:`AgentRun` rows in ``needs_approval`` state.
    """
    return list(
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


def fetch_run_principals(
    session: Any, *, pending_runs: list[AgentRun]
) -> dict[str, tuple[int, str]]:
    """Resolve each run principal email to ``(user_id, display_name)``.

    Args:
        session: SQLAlchemy session.
        pending_runs: Runs whose principals to resolve.

    Returns:
        ``email → (user_id, display_name)`` for every resolvable principal;
        empty when no run carries a principal.
    """
    principal_emails = {r.principal for r in pending_runs if r.principal}
    if not principal_emails:
        return {}
    return {
        str(email): (int(uid), str(name))
        for uid, email, name in session.execute(
            select(User.id, User.email, User.display_name).where(User.email.in_(principal_emails))
        ).all()
    }


def fetch_open_signals(session: Any, *, workspace_id: int, limit: int) -> list[ActionableSignal]:
    """Return open actionable signals, newest first.

    Args:
        session: SQLAlchemy session.
        workspace_id: Active workspace.
        limit: Row cap.

    Returns:
        The open :class:`ActionableSignal` rows.
    """
    return list(
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


def fetch_needs_action_count(session: Any, *, workspace_id: int) -> int:
    """Return the count of pending approvals + open signals (the ``act`` tier).

    Counted independently of the row slice so a capped fetch never
    under-reports what is waiting.

    Args:
        session: SQLAlchemy session.
        workspace_id: Active workspace.

    Returns:
        The combined needs-action count.
    """
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
    return int(pending_count or 0) + int(signal_count or 0)


def fetch_seen_at(session: Any, *, caller_id: int, workspace_id: int) -> datetime.datetime | None:
    """Return the caller's feed seen-cursor, normalised to UTC.

    SQLite drops the offset on a ``DateTime(timezone=True)`` column, so the
    cursor read back is naive; it is normalised to UTC before any
    comparison against the (UTC-aware) parsed row timestamps.

    Args:
        session: SQLAlchemy session.
        caller_id: Reader user id.
        workspace_id: Active workspace.

    Returns:
        The seen-cursor datetime (UTC-aware), or ``None`` when the reader
        has no marker yet.
    """
    seen_at = session.execute(
        select(FeedReadMarker.seen_at).where(
            FeedReadMarker.user_id == caller_id,
            FeedReadMarker.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if seen_at is not None and seen_at.tzinfo is None:
        seen_at = seen_at.replace(tzinfo=datetime.UTC)
    return seen_at


def fetch_unread_for_you_count(session: Any, *, caller_id: int, workspace_id: int) -> int:
    """Return the count of unread ``for_you`` notifications.

    Legacy rows written before the ``attention`` column existed count as
    ``for_you`` only when their event type is a mention.

    Args:
        session: SQLAlchemy session.
        caller_id: Recipient user id.
        workspace_id: Active workspace.

    Returns:
        The unread for-you count.
    """
    return int(
        session.execute(
            select(func.count())
            .select_from(UserNotification)
            .where(
                UserNotification.recipient_user_id == caller_id,
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


def fetch_mention_rows(
    session: Any, *, caller_id: int, workspace_id: int, fqn_map: dict[int, str]
) -> list[dict[str, Any]]:
    """Return feed rows for comments that mention the caller.

    Args:
        session: SQLAlchemy session.
        caller_id: The mentioned user id to match.
        workspace_id: Active workspace.
        fqn_map: Per-request DP-FQN cache for URL building.

    Returns:
        The serialized mention rows.
    """
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
        if caller_id in mentioned:
            mention_rows.append(row_from_comment(c, fqn_map, mention_actor_names, None))
    return mention_rows


def fetch_my_rows(
    session: Any, *, caller_id: int, fqn_map: dict[int, str], limit: int
) -> list[dict[str, Any]]:
    """Return feed rows for comments + reviews the caller authored.

    Args:
        session: SQLAlchemy session.
        caller_id: Author user id.
        fqn_map: Per-request DP-FQN cache for URL building.
        limit: Per-table row cap.

    Returns:
        The serialized authored rows (comments then reviews).
    """
    mine_comments = (
        session.execute(
            select(DataProductComment)
            .where(
                DataProductComment.author_user_id == caller_id,
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
            .where(DataProductReview.author_user_id == caller_id)
            .order_by(DataProductReview.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    my_actor_names = build_actor_names(session, list(mine_comments) + list(mine_reviews))
    return [row_from_comment(c, fqn_map, my_actor_names, None) for c in mine_comments] + [
        row_from_review(r, fqn_map, my_actor_names, None) for r in mine_reviews
    ]


def fetch_trending_counts(
    session: Any, *, workspace_id: int, cutoff: datetime.datetime, limit: int
) -> list[Any]:
    """Return ``(kind, ref, count)`` activity aggregates for the trending rail.

    Aggregates ``user_notifications`` grouped by source entity over the
    window, count descending.

    Args:
        session: SQLAlchemy session.
        workspace_id: Active workspace.
        cutoff: Lower bound on ``created_at`` (the window start).
        limit: Row cap.

    Returns:
        ``(source_entity_kind, source_entity_ref, count)`` rows.
    """
    return session.execute(
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
        .limit(limit)
    ).all()


def fetch_people_activity_counts(
    session: Any, *, workspace_id: int, cutoff: datetime.datetime
) -> tuple[list[Any], list[Any]]:
    """Return per-author comment + review counts in the window.

    Counts the two tables separately so the caller can sum them
    client-side, keeping the SQL portable across SQLite + Postgres.

    Args:
        session: SQLAlchemy session.
        workspace_id: Active workspace.
        cutoff: Lower bound on ``created_at`` (the window start).

    Returns:
        ``(comment_counts, review_counts)`` — each a list of
        ``(author_user_id, count)`` rows.
    """
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
    return comment_counts, review_counts


def fetch_display_names(session: Any, *, user_ids: list[int]) -> dict[int, str]:
    """Return ``user_id → display_name`` for the given ids.

    Args:
        session: SQLAlchemy session.
        user_ids: Users to resolve.

    Returns:
        The display-name map.
    """
    return dict(
        session.execute(select(User.id, User.display_name).where(User.id.in_(user_ids))).all()
    )
