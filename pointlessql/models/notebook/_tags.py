"""Notebook-level lifecycle tags.

Tags categorise a notebook in the workspace tree (``draft`` / ``etl``
/ ``prod`` / etc.).  Distinct from cell-tags which sit inside the
notebook source via the marker grammar.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookTag(Base):
    """Notebook-level lifecycle tags.

    Tags categorise a notebook in the workspace tree (``draft`` /
    ``etl`` / ``prod`` / etc.).  Different from
    :data:`pointlessql.services.notebook.cell_tags.CURATED_CELL_TAGS`
    — those tag *cells inside* a notebook via the marker grammar,
    while a :class:`NotebookTag` tags the *notebook itself* so the
    workspace tree can filter by tag.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete so a
            removed notebook drops its tag rows too.
        tag: Lowercase tag string; the route normalises before write.
        created_at: When the tag was attached; surfaces in audit.
    """

    __tablename__ = "notebook_tags"

    __table_args__ = (
        UniqueConstraint(
            "notebook_id",
            "tag",
            name="uq_notebook_tags_notebook_tag",
        ),
        Index("ix_notebook_tags_tag", "tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
