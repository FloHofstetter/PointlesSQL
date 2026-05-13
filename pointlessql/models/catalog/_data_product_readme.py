"""Versioned per-DP READMEs (Phase 71.5).

One table:

* ``data_product_readmes`` — one row per *version* of a product's
  README.  ``version_int`` is monotonic per
  ``(workspace_id, data_product_id)``; latest = max.  Older
  versions stay on disk to support the History modal + side-by-
  side diff view.

No soft-delete: an explicit "delete README" UX isn't part of
Phase 71.  The history rows survive contract-yaml deletes only
via cascade (we want them gone too).
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


class DataProductReadme(Base):
    """One historical version of a data product's README.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'`` so a yaml deletion also wipes
            the README history.
        version_int: Monotonic counter per
            ``(workspace_id, data_product_id)``.  UNIQUE
            constraint enforces no two versions share a number.
        body_md: Markdown body.  May be the empty string when the
            steward explicitly publishes a blank README.
        updated_by_user_id: FK on ``users.id`` — who last saved.
        updated_at: Wall-clock at save time.
    """

    __tablename__ = "data_product_readmes"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "version_int",
            name="uq_dp_readme_versioned",
        ),
        Index(
            "ix_dp_readme_dp_version",
            "data_product_id",
            "version_int",
        ),
        Index(
            "ix_data_product_readmes_social_target",
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
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Phase 77.0.B — polymorphic anchor (see _data_product_comments.py).
    social_target_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=True,
    )
    version_int: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
