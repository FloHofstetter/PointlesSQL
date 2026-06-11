"""Genie spaces — curated natural-language data rooms.

Three tables back the AI/BI-Genie-shaped surface:

* ``genie_spaces`` — one curated room per row: a slug-addressable,
  owned scope of tables + metric views the LLM is allowed to answer
  over, plus freeform curator instructions.
* ``genie_trusted_assets`` — curator-approved question → SQL pairs.
  They serve double duty: few-shot examples prepended to the LLM
  prompt AND directly runnable chips in the room UI ("trusted"
  means a human vouched for the SQL).
* ``genie_messages`` — the room transcript.  V1 keeps one shared
  room per space (a flat per-space history every workspace user
  reads and appends to) rather than per-user threads; the
  ``user_id`` column records who asked so a threaded follow-up can
  split the history without a backfill.

Visibility mirrors the BI-dashboard surface: every logged-in
workspace user can view and ask, owner + admins curate (tables,
metric views, instructions, trusted assets).
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

GENIE_MESSAGE_ROLES: tuple[str, ...] = ("user", "assistant")
"""Allowed values for :attr:`GenieMessage.role`."""

GENIE_MESSAGE_STATUSES: tuple[str, ...] = ("ok", "error")
"""Allowed values for :attr:`GenieMessage.status`."""

GENIE_FEEDBACK_VALUES: tuple[str, ...] = ("up", "down")
"""Allowed non-``NULL`` values for :attr:`GenieMessage.feedback`."""


class GenieSpace(Base):
    """One curated natural-language data room.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; hard isolation
            boundary like every other metadata row.
        slug: URL-visible identifier, unique across all rows
            (slugified title + random suffix, mirroring
            ``bi_dashboards.slug`` semantics).
        title: Human-readable name.
        description: Optional free-form description shown on the
            spaces list.
        instructions: Optional freeform curator guidance prepended
            to every LLM prompt (business definitions, preferred
            filters, naming conventions).
        tables: JSON-encoded list of three-part
            ``catalog.schema.table`` FQNs the space is allowed to
            query.  Generated SQL referencing anything outside this
            list is rejected before execution.
        metric_views: JSON-encoded list of metric-view full names
            whose dimensions / measures are offered to the LLM as
            semantic-layer context.
        owner_id: FK to ``users.id`` — the creator; mutations are
            owner + admin only.
        created_at: Timestamp when the space was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "genie_spaces"

    __table_args__ = (
        Index("ix_genie_spaces_workspace", "workspace_id"),
        Index("ix_genie_spaces_owner", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    metric_views: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GenieTrustedAsset(Base):
    """One curator-approved question → SQL example for a space.

    Attributes:
        id: Auto-incremented primary key.
        space_id: FK to :class:`GenieSpace` with ``ON DELETE
            CASCADE`` — assets follow their room.
        question: The natural-language phrasing the SQL answers.
        sql_text: The vetted single-SELECT SQL.
        created_by: FK to ``users.id`` — the curator who approved
            it (directly or by promoting an assistant answer).
        created_at: Timestamp when the asset was added.
    """

    __tablename__ = "genie_trusted_assets"

    __table_args__ = (Index("ix_genie_trusted_assets_space", "space_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("genie_spaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GenieMessage(Base):
    """One turn in a space's shared transcript.

    Attributes:
        id: Auto-incremented primary key.
        space_id: FK to :class:`GenieSpace` with ``ON DELETE
            CASCADE`` — the transcript follows its room.
        user_id: FK to ``users.id`` for ``user`` turns; nullable so
            assistant rows (and rows whose author was deleted) stay
            valid.
        role: One of :data:`GENIE_MESSAGE_ROLES`.
        content: Natural-language text — the question on ``user``
            rows, a short status / explanation line on ``assistant``
            rows.
        sql_text: The generated SQL on ``assistant`` rows; ``NULL``
            on user rows and on assistant rows that failed before
            SQL was produced.
        status: One of :data:`GENIE_MESSAGE_STATUSES`; ``error``
            marks assistant turns whose SQL was rejected or whose
            execution failed.
        error: Human-readable failure detail on ``error`` rows.
        feedback: ``up`` / ``down`` / ``NULL`` — reader reaction on
            assistant rows; a thumbs-up answer is the promotion
            candidate for the trusted-asset list.
        created_at: Wall-clock at row insert; the index orders the
            room transcript chronologically.
    """

    __tablename__ = "genie_messages"

    __table_args__ = (
        Index("ix_genie_messages_space_created", "space_id", "created_at"),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_genie_messages_role",
        ),
        CheckConstraint(
            "status IN ('ok', 'error')",
            name="ck_genie_messages_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    space_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("genie_spaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
