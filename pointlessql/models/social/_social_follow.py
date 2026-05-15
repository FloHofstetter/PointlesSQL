"""Polymorphic follow rows for non-DP entity kinds (Phase 77.8).

The legacy ``data_product_follows`` table has a composite PK on
``(workspace_id, data_product_id, user_id)`` that 77.0.G couldn't
relax without an SQLite-unfriendly PK swap.  77.8 sidesteps that
by introducing a sibling polymorphic table — kind-agnostic from
day 1, keyed by ``(workspace_id, social_target_id, user_id)``.

The DP follow route keeps using ``data_product_follows``
unchanged (zero behaviour drift).  Polymorphic follows for
tables / models / branches / runs / etc. land in this table
through the upcoming ``/api/social/{kind}/{ref}/follow`` path.

Phase 77.11 collapses the two tables into one — keeps the legacy
DP follow rows in the same place as polymorphic rows.  Until
then, ``fanout_event`` queries both tables (DP via legacy, non-DP
via this table) so the inbox keeps working uniformly.
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
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
