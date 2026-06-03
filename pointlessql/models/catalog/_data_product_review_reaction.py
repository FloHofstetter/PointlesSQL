"""Reactions on data-product reviews.

One row per ``(review, user, emoji)`` triple — GitHub-style, the
exact shape comment reactions use.  Reviews of one data product all
share that product's polymorphic anchor, so reactions key on the
``review_id`` PK (not the shared anchor) — otherwise every sibling
review of the same product would move as one count.

Six-emoji canonical set lives in
:mod:`pointlessql.api.data_products_routes.reactions` to avoid an
import cycle back into models.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductReviewReaction(Base):
    """One emoji reaction by one user on one review.

    Attributes:
        review_id: FK on ``data_product_reviews.id`` with
            ``ondelete='CASCADE'`` — the key the reaction belongs to,
            so each review owns its own counts even though sibling
            reviews share one social anchor.
        user_id: FK on ``users.id`` with ``ondelete='CASCADE'``.
        emoji: Canonical emoji glyph (one of the GitHub-6 set).
        created_at: Wall-clock at POST time.
        social_target_id: Polymorphic anchor — matches the parent
            review's target (the data product's), mirroring how
            comment reactions carry the parent comment's anchor.
    """

    __tablename__ = "data_product_review_reactions"

    __table_args__ = (
        PrimaryKeyConstraint(
            "review_id",
            "user_id",
            "emoji",
            name="pk_dp_review_reactions",
        ),
        Index("ix_dp_review_reactions_review", "review_id"),
        Index(
            "ix_data_product_review_reactions_social_target",
            "social_target_id",
        ),
    )

    review_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
