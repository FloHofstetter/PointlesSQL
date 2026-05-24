"""User-to-user follow link.

Composite-PK ``(follower_user_id, followed_user_id)``.  Soft-
delete is intentionally NOT modelled — the row either exists
(``follow``) or it doesn't (``unfollow``).  A DB-level CHECK
``follower != followed`` prevents self-follow even if a future
route handler forgets the app-level guard.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class UserFollow(Base):
    """One follower→followed link.

    Attributes:
        follower_user_id: User who clicked Follow.  FK + CASCADE.
        followed_user_id: User being followed.  FK + CASCADE.
        created_at: Wall-clock when the follow was created.
    """

    __tablename__ = "user_follows"

    __table_args__ = (
        PrimaryKeyConstraint(
            "follower_user_id",
            "followed_user_id",
            name="pk_user_follows",
        ),
        CheckConstraint(
            "follower_user_id <> followed_user_id",
            name="ck_user_follows_no_self",
        ),
        Index(
            "ix_user_follows_followed",
            "followed_user_id",
            "created_at",
        ),
    )

    follower_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    followed_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
