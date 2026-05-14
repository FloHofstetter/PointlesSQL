"""Typed manual endorsements per data product (Phase 72.4).

Four allowed types, CHECK-constrained at the DB layer:

* ``verified-by-steward`` — the steward has rubber-stamped the
  contract and the latest contents.
* ``production-ready`` — promoted for downstream consumption.
* ``deprecated`` — soft warning on writes; Phase-50 pre-write
  hook reads this on a future polish sprint.
* ``under-review`` — actively being audited; readers should
  expect schema churn.

Soft-delete model: a row never disappears.  Applying then
removing the same type leaves *two* rows behind (one with
``removed_at`` set, one with it ``NULL``).  The composite
UNIQUE (workspace, dp, type, removed_at) lets ``NULL`` and
non-NULL coexist (most engines treat NULL as distinct in unique
indexes; SQLite + PG both honour this), so the "only one
active row per (dp, type)" invariant holds.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

ENDORSEMENT_TYPES: tuple[str, ...] = (
    "verified-by-steward",
    "production-ready",
    "deprecated",
    "under-review",
)


class DataProductEndorsement(Base):
    """One typed endorsement on a data product.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id``,
            ``ondelete='CASCADE'``.
        endorsement_type: One of :data:`ENDORSEMENT_TYPES`.
        applied_by_user_id: Who applied the endorsement.  Always
            a human — caller when direct, agent's principal when
            ``applied_by_agent_id`` is set (Phase 76.5.1).
        applied_by_agent_id: Optional agent identity that posted
            the endorsement on behalf of the principal.  When set,
            the UI renders the endorsement as authored *by the
            agent on behalf of* the principal.  Nullable.
        applied_at: Wall-clock at apply.
        removed_at: ``None`` while active; wall-clock at remove.
        note_md: Optional free-form context.
    """

    __tablename__ = "data_product_endorsements"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "endorsement_type",
            "removed_at",
            name="uq_dp_endorsement_active",
        ),
        CheckConstraint(
            "endorsement_type IN ('verified-by-steward', 'production-ready', "
            "'deprecated', 'under-review')",
            name="ck_dp_endorsement_type",
        ),
        Index(
            "ix_dp_endorsement_dp_type",
            "data_product_id",
            "endorsement_type",
        ),
        Index(
            "ix_data_product_endorsements_social_target",
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
    data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Phase 77.0.B — polymorphic anchor (see _data_product_comments.py).
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
    endorsement_type: Mapped[str] = mapped_column(Text, nullable=False)
    applied_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    applied_by_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    removed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
