"""Per-user sticky badge row (Phase 76.2).

Badges are positive-only awards rolled forward by the
``_user_badges_loop`` background task.  ``UNIQUE(user_id,
badge_key)`` so the awarding loop is naturally idempotent — the
loop INSERTs a new row when the threshold is met and the absence
of a delete path means a badge can never be revoked.

The ``awarded_for_count`` column persists the metric value at
award time (e.g. ``100`` for ``reviewer_100plus``) so the profile
page can render context next to the badge without recomputing.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

BADGE_KEYS: tuple[str, ...] = (
    "steward_3plus",
    "reviewer_100plus",
    "mention_magnet_20plus",
    "accepted_answer_5plus",
    "endorser_50plus",
)


class UserBadge(Base):
    """One awarded badge for one user.

    Attributes:
        id: Surrogate primary key.
        user_id: FK on ``users.id`` with ``ondelete='CASCADE'``.
        badge_key: Stable enum identifier (member of
            :data:`BADGE_KEYS`).
        awarded_at: Wall-clock when the loop awarded the badge.
        awarded_for_count: Optional integer captured at award time
            (e.g. 100 for ``reviewer_100plus``).
    """

    __tablename__ = "user_badges"

    __table_args__ = (
        UniqueConstraint("user_id", "badge_key", name="uq_user_badge"),
        Index("ix_user_badges_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    badge_key: Mapped[str] = mapped_column(String(40), nullable=False)
    awarded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    awarded_for_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
