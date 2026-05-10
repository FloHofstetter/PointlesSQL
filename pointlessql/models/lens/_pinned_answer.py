"""Lens pinned answer — bookmarked assistant message rendered standalone.

When an analyst likes an answer they pin it.  The pin captures a
snapshot of the answer (the assistant message text plus the most
recent SQL tool-call's result) plus a stable slug so the URL
``/lens/pinned/<slug>`` survives the source session being deleted.

Visibility mirrors :class:`SavedQuery`: owner + admins always see;
``is_shared=True`` extends to every workspace member.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class LensPinnedAnswer(Base):
    """One pinned Lens answer addressable by stable slug.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace the pin belongs to.  Hard isolation:
            cross-workspace reads are blocked even when the slug
            matches.
        owner_id: User who created the pin.
        slug: URL-safe slug, unique per workspace.  Auto-generated
            from the title at create time with ``-2`` / ``-3`` /
            etc. suffix on collision.
        title: Short human label (≤ 200 chars).
        source_message_id: The :class:`LensMessage` (assistant role)
            whose content the pin captured.  Nullable so that
            deleting the source session does not orphan the pin —
            the snapshot in ``content_snapshot`` keeps the answer
            renderable.
        content_snapshot: Frozen copy of the assistant message text
            at pin time.  Survives source-session deletion.
        sql_text: Optional — if the answer was driven by a SQL tool
            call, the SQL is captured here so the pinned page can
            "Re-run".  ``NULL`` for non-SQL answers.
        result_preview: JSON snapshot of the SQL result (columns +
            first N rows) at pin time.  ``NULL`` for non-SQL
            answers.
        is_shared: When ``True`` every workspace member sees the
            pin; when ``False`` only owner + admins.
        created_at: Wall-clock at pin time.
        updated_at: Wall-clock at last edit (title rename).
    """

    __tablename__ = "lens_pinned_answers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_lens_pinned_workspace_slug"),
        Index("ix_lens_pinned_workspace_owner", "workspace_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("lens_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_preview: Mapped[object | None] = mapped_column(JSON, nullable=True)
    is_shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
