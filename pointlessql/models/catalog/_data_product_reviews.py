"""Star ratings + text reviews per data product (Phase 71.2).

One table:

* ``data_product_reviews`` — one row per ``(workspace_id, data_product_id,
  author_user_id)`` triple (unique constraint).  Captures stars,
  free-form markdown body, and the data product's SemVer at write
  time so a future "is this still relevant on v1.3?" UX can light up
  without a migration.

Reviews are hard-deleted (DELETE removes the row).  Aggregates
(average stars + count) are computed on read; no cached column.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductReview(Base):
    """One user's review of a data product.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.  Nullable since the Phase 77.0
            polymorphism shift — the kind-agnostic join key is
            ``social_target_id``.
        social_target_id: Phase 77.0.B polymorphic anchor (joined
            through ``social_targets``).  The Phase 77.2.1 UNIQUE
            ``uq_dp_review_polymorphic_one_per_user`` keys on this
            column rather than on ``data_product_id`` directly.
        author_user_id: FK on ``users.id``.  ``(workspace_id,
            data_product_id, author_user_id)`` is unique — one
            review per user per product.  Always a human — caller
            when direct, agent's principal when
            ``author_agent_id`` is set (Phase 76.5.1).
        author_agent_id: Optional agent identity that authored the
            review on behalf of the principal.  When set, the UI
            renders the review as authored *by the agent on behalf
            of* the principal.  Nullable.
        stars: 1..5, enforced by a CHECK constraint.
        body_md: Free-form markdown body (may be empty when the
            user only wants to express a star rating).
        dp_version_at_review: SemVer snapshot of the DP's
            ``version`` at write time.
        created_at: Wall-clock at first PUT.
        updated_at: Wall-clock at most-recent PUT (idempotent
            upsert).
    """

    __tablename__ = "data_product_reviews"

    __table_args__ = (
        # Phase 77.2.1 — kind-agnostic upsert idempotency.  Phase
        # 78 polish dropped the legacy DP-only UNIQUE because this
        # one already covers DP rows via the 1:1
        # ``social_targets.data_product_id`` back-pointer.
        UniqueConstraint(
            "workspace_id",
            "social_target_id",
            "author_user_id",
            name="uq_dp_review_polymorphic_one_per_user",
        ),
        CheckConstraint("stars BETWEEN 1 AND 5", name="ck_dp_review_stars_range"),
        Index("ix_dp_reviews_dp_stars", "data_product_id", "stars"),
        Index(
            "ix_data_product_reviews_social_target",
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
    author_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    author_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dp_version_at_review: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
