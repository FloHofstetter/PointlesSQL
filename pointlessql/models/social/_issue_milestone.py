"""Workspace-scoped milestone for tracked issues.

A milestone groups issues by a due date / planning bucket — same
shape as GitHub milestones.  Each issue references at most one
milestone (mirrors GitHub, by design).
The catalogue is workspace-scoped so two workspaces can have
identically-titled milestones without collision.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class IssueMilestone(Base):
    """A milestone grouping one or more issues by planning bucket.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        title: Human-readable name (max 200 chars).
        description_md: Optional long-form markdown blurb.  ``None``
            when the milestone is just a date marker without prose.
        due_at: Planned closure timestamp; ``None`` for open-ended
            milestones.
        closed_at: Wall-clock when the milestone was closed; ``None``
            while still open.
        created_at: Wall-clock when the milestone was created.
    """

    __tablename__ = "issue_milestones"

    __table_args__ = (Index("ix_issue_milestones_workspace", "workspace_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
