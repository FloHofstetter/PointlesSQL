"""Versioned per-entity READMEs.

Phase 71.5 shipped this table as ``data_product_readmes``.  77.0.B
added the polymorphic ``social_target_id`` anchor so non-DP kinds
could carry their own README history.  Phase 78 polish dropped
the DP-only ``data_product_id`` column + renamed the table to
``entity_readmes`` to make the polymorphic shape primary.

One row per *version* of an entity's README.  ``version_int`` is
monotonic per ``(workspace_id, social_target_id)``; latest = max.
Older versions stay on disk to support the History modal + side-
by-side diff view.

No soft-delete: an explicit "delete README" UX isn't part of the
surface.  History rows survive the entity yaml delete only via
``social_targets`` cascade (we want them gone too).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class EntityReadme(Base):
    """One historical version of an entity's README.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        social_target_id: FK on ``social_targets.id`` — the
            polymorphic anchor for the entity that owns this
            README.
        version_int: Monotonic counter per
            ``(workspace_id, social_target_id)``.  UNIQUE
            constraint enforces no two versions share a number.
        body_md: Markdown body.  May be the empty string when the
            steward explicitly publishes a blank README.
        updated_by_user_id: FK on ``users.id`` — who last saved.
        updated_at: Wall-clock at save time.
    """

    __tablename__ = "entity_readmes"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "social_target_id",
            "version_int",
            name="uq_entity_readme_versioned",
        ),
        Index(
            "ix_entity_readmes_target_version",
            "social_target_id",
            "version_int",
        ),
        Index(
            "ix_entity_readmes_social_target",
            "social_target_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
    version_int: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
