"""Lightweight per-user star bookmarks.

Stars are the "I bookmarked this, no notifications" primitive.
They sit alongside the follow table — follows generate
inbox rows on relevant events, stars are inert.

The table is polymorphic from day 1: composite PK on
``(workspace_id, user_id, social_target_id)``.  Adding a new
entity kind needs no migration; just register the kind in
:mod:`entity_registry` and the polymorphic star endpoint covers
it transparently.

No soft-delete: a DELETE drops the row outright.  The audit-mirror
records the star/unstar event so the trail survives.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SocialStar(Base):
    """One user-stars-entity bookmark row.

    Attributes:
        workspace_id: PK part 1 + tenant scope.
        user_id: PK part 2.  ``ondelete='CASCADE'`` keeps the table
            tidy when a user is deleted.
        social_target_id: PK part 3.  ``ondelete='CASCADE'`` keeps
            the table tidy when the parent entity goes away.
        created_at: Wall-clock when the star was created.
    """

    __tablename__ = "social_stars"

    __table_args__ = (
        PrimaryKeyConstraint(
            "workspace_id",
            "user_id",
            "social_target_id",
            name="pk_social_stars",
        ),
        Index("ix_social_stars_target", "social_target_id"),
        Index("ix_social_stars_user", "user_id", "social_target_id"),
    )

    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
