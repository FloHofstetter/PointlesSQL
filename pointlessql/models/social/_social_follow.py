"""Polymorphic follow rows for every entity kind.

replaces the legacy ``data_product_follows`` (which had a
composite PK on ``(workspace_id, data_product_id, user_id)`` that
the polymorphic rewrite could not relax without an SQLite-
unfriendly PK swap).  Every follow — DP or otherwise — now lives
in this table keyed by
``(workspace_id, social_target_id, user_id)``.

DP follower lookups join through :class:`SocialTarget` (where
``entity_kind='dp'`` and ``data_product_id`` is the back-pointer)
to recover the legacy DP affinity at query time.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SocialFollow(Base):
    """One user-follows-entity link for non-DP kinds.

    Attributes:
        workspace_id: PK part 1 + tenant scope.
        social_target_id: PK part 2.  ``ondelete='CASCADE'`` keeps
            the table tidy when the polymorphic anchor goes away.
        user_id: PK part 3.  ``ondelete='CASCADE'`` keeps the
            table tidy when a user is removed.
        created_at: Wall-clock when the follow link was created.
    """

    __tablename__ = "social_follows"

    __table_args__ = (
        PrimaryKeyConstraint(
            "workspace_id",
            "social_target_id",
            "user_id",
            name="pk_social_follows",
        ),
        Index("ix_social_follows_user", "user_id", "created_at"),
    )

    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
