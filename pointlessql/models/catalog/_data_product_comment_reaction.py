"""Reactions on data-product comments.

One row per ``(comment, user, emoji)`` triple — GitHub-style.
A user may add multiple emoji to the same comment but only one
row per emoji-kind.  Idempotent inserts use ``ON CONFLICT
DO NOTHING`` (or the SQLAlchemy equivalent) to keep the route
handler clean.

Six-emoji canonical set lives in
:mod:`pointlessql.api.data_products_routes.reactions` to avoid
import cycles back into models.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductCommentReaction(Base):
    """One emoji reaction by one user on one comment.

    Attributes:
        comment_id: FK on ``data_product_comments.id`` with
            ``ondelete='CASCADE'``.
        user_id: FK on ``users.id`` with ``ondelete='CASCADE'``.
        emoji: Canonical emoji glyph (one of the GitHub-6 set).
        created_at: Wall-clock at POST time.
        social_target_id: Polymorphic anchor (matches the parent
            comment's target — comment-reactions do not own a
            separate anchor).
    """

    __tablename__ = "data_product_comment_reactions"

    __table_args__ = (
        PrimaryKeyConstraint(
            "comment_id",
            "user_id",
            "emoji",
            name="pk_dp_comment_reactions",
        ),
        Index("ix_dp_comment_reactions_comment", "comment_id"),
        Index(
            "ix_data_product_comment_reactions_social_target",
            "social_target_id",
        ),
    )

    comment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_comments.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # polymorphic anchor (see _data_product_comments.py).
    # On a comment-reaction the anchor matches the *comment's* target,
    # not a separate one — see services/social/_target_resolver.py.
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
