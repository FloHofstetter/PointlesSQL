"""Consumer-contributed metadata: use cases + votes + ratings.

Three tables that let consumers of a data product feed back into the
discovery surface:

* :class:`DataProductUseCase` — a short prose card any authenticated
  user can post about how they (intend to) use the product.
* :class:`DataProductUseCaseVote` — one vote per (use case, user); the
  service-layer aggregator counts votes back onto the parent use case.
* :class:`DataProductRating` — one row per (product, user) carrying a
  1–5 score + optional comment, upserted on each call.

All three CASCADE on ``data_products.id`` / ``data_product_use_cases.id``
/ ``users.id`` so deleting a product or a user removes their
contributions.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductUseCase(Base):
    """One use-case card a consumer posted about a product.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE.
        title: Short title (max 200 chars).
        body: Free-form prose.
        author_user_id: Nullable FK on ``users.id``.
        votes: Cached vote count (the votes table is the truth; the
            service layer updates this column on each vote/unvote).
        created_at: Wall-clock first insert.
        updated_at: Wall-clock last edit.
    """

    __tablename__ = "data_product_use_cases"

    __table_args__ = (
        Index(
            "ix_dp_use_cases_product_votes",
            "data_product_id",
            "votes",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    author_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductUseCaseVote(Base):
    """One vote of one user on one use case (composite PK)."""

    __tablename__ = "data_product_use_case_votes"

    use_case_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_use_cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductRating(Base):
    """One 1..5 score per (product, user), upserted on each call.

    Attributes:
        data_product_id: Composite primary key; FK CASCADE.
        user_id: Composite primary key; FK CASCADE.
        score: Integer 1..5 enforced by SQL CHECK.
        comment: Optional free-form note.
        created_at: First-insert wall-clock.
        updated_at: Last-upsert wall-clock.
    """

    __tablename__ = "data_product_ratings"

    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 5", name="ck_dp_ratings_score_range"),)

    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
