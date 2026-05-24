"""Workspace pinned-entity rows.

A workspace landing page (``/workspaces/{slug}``) displays a
small admin-curated gallery of pinned entities — analogous to a
GitHub organisation's "Pinned repositories" surface but
polymorphic across every registered entity kind.

Each row links a workspace to a ``social_targets`` anchor with a
``pin_order`` for drag-and-drop reordering and a
``pinned_by_user_id`` for the audit trail.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class WorkspacePinnedEntity(Base):
    """One workspace-pinned polymorphic entity.

    Attributes:
        workspace_id: PK part 1 — tenant scope.
        social_target_id: PK part 2 — polymorphic anchor row.
            ``ondelete='CASCADE'`` so the pin disappears when the
            target entity is deleted.
        pin_order: Display order on the landing page (admin
            drag-and-drop sets this).
        pinned_by_user_id: Audit-trail FK to the admin who pinned
            the row.
        pinned_at: Wall-clock when the pin was added.
    """

    __tablename__ = "workspace_pinned_entities"

    __table_args__ = (
        PrimaryKeyConstraint(
            "workspace_id",
            "social_target_id",
            name="pk_workspace_pinned_entities",
        ),
        Index(
            "ix_workspace_pinned_entities_order",
            "workspace_id",
            "pin_order",
        ),
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
    pin_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    pinned_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    pinned_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
