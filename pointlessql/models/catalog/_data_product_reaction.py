"""Reactions on data products themselves (Phase 76.1).

Mirror of :class:`DataProductCommentReaction` but the target is
the product, not a single comment.  Rendered as a row above the
Discussion-tab comment list so visitors get a quick aggregate of
sentiment toward the product.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductReaction(Base):
    """One emoji reaction by one user on one data product.

    Attributes:
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.
        user_id: FK on ``users.id`` with ``ondelete='CASCADE'``.
        emoji: Canonical emoji glyph (one of the GitHub-6 set).
        created_at: Wall-clock at POST time.
    """

    __tablename__ = "data_product_reactions"

    __table_args__ = (
        PrimaryKeyConstraint(
            "data_product_id",
            "user_id",
            "emoji",
            name="pk_dp_reactions",
        ),
        Index("ix_dp_reactions_dp", "data_product_id"),
        Index(
            "ix_data_product_reactions_social_target",
            "social_target_id",
        ),
    )

    data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Phase 77.0.B — polymorphic anchor (see _data_product_comments.py).
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
