"""Workspace-scoped label catalogue for tracked issues.

Labels are user-defined slugs (e.g. ``bug``, ``good-first-issue``,
``compliance``) attached to issues via the ``issues.labels_json``
JSON array.  No M:N junction — per the Phase-77 plan, labels live
as a slug list inside each issue row.  Filtering-by-label goes
through 77.9 FTS or client-side; the SQL-side cost of a junction
table wasn't worth it for the typical workspace label count.

The catalogue row itself stores presentation metadata: human-
readable ``label_text`` (separate from the slug so the display
can be renamed without rewriting every issue's ``labels_json``)
and a ``color_hex`` value for the chip background.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class IssueLabel(Base):
    """One workspace-scoped label definition.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope; ``(workspace_id, slug)`` is unique.
        slug: Machine-readable identifier (max 40 chars).  Stored on
            issues inside the ``labels_json`` array.
        label_text: Human-readable display text (max 80 chars).
        color_hex: 7-char ``#rrggbb`` chip background colour.
            Defaults to ``#cccccc`` (neutral grey) when the creator
            doesn't pick a colour.
        created_at: Wall-clock when the label was created.
    """

    __tablename__ = "issue_labels"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "slug",
            name="uq_issue_labels_slug_per_workspace",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    label_text: Mapped[str] = mapped_column(String(80), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False, server_default="#cccccc")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
