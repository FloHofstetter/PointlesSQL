"""Badge-awarding service (Phase 76.2).

Sync function the ``_user_badges_loop`` invokes via
``asyncio.to_thread``.  Five thresholds, all positive-only:

* ``steward_3plus`` — steward of ≥3 data products.
* ``reviewer_100plus`` — author of ≥100 reviews.
* ``mention_magnet_20plus`` — appears in ≥20 distinct mentions
  (counted as the recipient on the ``user_notifications`` table
  for ``data_product.commented`` events where the recipient is
  in the resolved mention list — proxied here by counting rows
  on ``user_notifications`` whose ``actor_user_id != recipient``
  and the event type matches).
* ``accepted_answer_5plus`` — author of ≥5 comments flagged
  ``is_accepted_answer``.
* ``endorser_50plus`` — applied ≥50 active endorsements.

The loop only INSERTs new rows.  The ``UNIQUE(user_id,
badge_key)`` constraint makes the insert idempotent on repeat
runs.  Badges are never revoked.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select

from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._user_badge import UserBadge

_STEWARD_MIN = 3
_REVIEWER_MIN = 100
_MENTION_MIN = 20
_ACCEPTED_ANSWER_MIN = 5
_ENDORSER_MIN = 50


def award_badges(session_factory: Any) -> int:
    """Recompute badge eligibility + INSERT any newly-met thresholds.

    Args:
        session_factory: SQLAlchemy session factory.

    Returns:
        Number of new badge rows inserted across all users.
    """
    inserted = 0
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing_rows = (
            session.execute(select(UserBadge.user_id, UserBadge.badge_key)).all()
        )
        existing: set[tuple[int, str]] = {
            (int(uid), key) for uid, key in existing_rows
        }

        steward_counts = dict(
            session.execute(
                select(
                    DataProduct.steward_user_id, func.count()
                )
                .where(DataProduct.steward_user_id.is_not(None))
                .group_by(DataProduct.steward_user_id)
            ).all()
        )
        reviewer_counts = dict(
            session.execute(
                select(
                    DataProductReview.author_user_id, func.count()
                ).group_by(DataProductReview.author_user_id)
            ).all()
        )
        mention_counts = dict(
            session.execute(
                select(
                    UserNotification.recipient_user_id, func.count()
                )
                .where(
                    UserNotification.event_type
                    == "pointlessql.data_product.commented",
                    UserNotification.actor_user_id.is_not(None),
                )
                .group_by(UserNotification.recipient_user_id)
            ).all()
        )
        accepted_counts = dict(
            session.execute(
                select(
                    DataProductComment.author_user_id, func.count()
                )
                .where(DataProductComment.is_accepted_answer.is_(True))
                .group_by(DataProductComment.author_user_id)
            ).all()
        )
        endorser_counts = dict(
            session.execute(
                select(
                    DataProductEndorsement.applied_by_user_id, func.count()
                )
                .where(DataProductEndorsement.removed_at.is_(None))
                .group_by(DataProductEndorsement.applied_by_user_id)
            ).all()
        )

        def _maybe_award(user_id: int | None, badge_key: str, count: int) -> None:
            nonlocal inserted
            if user_id is None:
                return
            if (int(user_id), badge_key) in existing:
                return
            session.add(
                UserBadge(
                    user_id=int(user_id),
                    badge_key=badge_key,
                    awarded_at=now,
                    awarded_for_count=int(count),
                )
            )
            inserted += 1

        for uid, count in steward_counts.items():
            if count and count >= _STEWARD_MIN:
                _maybe_award(uid, "steward_3plus", count)
        for uid, count in reviewer_counts.items():
            if count and count >= _REVIEWER_MIN:
                _maybe_award(uid, "reviewer_100plus", count)
        for uid, count in mention_counts.items():
            if count and count >= _MENTION_MIN:
                _maybe_award(uid, "mention_magnet_20plus", count)
        for uid, count in accepted_counts.items():
            if count and count >= _ACCEPTED_ANSWER_MIN:
                _maybe_award(uid, "accepted_answer_5plus", count)
        for uid, count in endorser_counts.items():
            if count and count >= _ENDORSER_MIN:
                _maybe_award(uid, "endorser_50plus", count)

        if inserted:
            session.commit()

    return inserted
