"""Polymorphic emoji reactions on any entity.

Replaces the original ``data_product_reactions`` table (which
later grew a polymorphic ``social_target_id`` UNIQUE on top).
This row carries the same shape but keys exclusively on
``social_target_id`` (the kind-agnostic polymorphic anchor).
DP reactions live here too — the social_target row's
``data_product_id`` back-pointer (when ``entity_kind='dp'``)
preserves the legacy affinity.

One row per ``(social_target_id, user_id, emoji)`` triple.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SocialReaction(Base):
    """One emoji reaction by one user on one polymorphic entity.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        social_target_id: FK on ``social_targets.id`` —
            ``ondelete='CASCADE'`` keeps the table tidy when the
            polymorphic anchor goes away.
        user_id: FK on ``users.id`` — ``ondelete='CASCADE'``.
        emoji: Canonical emoji glyph (one of the GitHub-6 set).
        created_at: Wall-clock at POST time.
    """

    __tablename__ = "social_reactions"

    __table_args__ = (
        UniqueConstraint(
            "social_target_id",
            "user_id",
            "emoji",
            name="uq_social_reactions_one_per_user_per_emoji",
        ),
        Index("ix_social_reactions_target", "social_target_id"),
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
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    emoji: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
