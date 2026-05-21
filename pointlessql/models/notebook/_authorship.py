"""Per-cell authorship attribution (Phase 101).

The "current attribution" surface on top of the Phase-96 provenance
log: who minted this cell and who last touched it.  Used by the
editor's cell-header chip and the reviewer-per-cell flow.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookCellAuthorship(Base):
    """Per-cell authorship attribution (Phase 101).

    The Phase-96 :class:`NotebookCellProvenance` table records every
    accepted AI-assistant proposal as an append-only audit log.
    Authorship is the *current* attribution surface: "who minted this
    cell and who last touched it".  Used by the editor's cell-header
    chip ("agent A • last edited by user B") and by the reviewer-per-
    cell flow so a reviewer agent can see at a glance whether the
    cell came from a human or a fellow agent.

    One row per :class:`NotebookCellIdentity.id` (1:1).  The save-path
    reconciler upserts on every save: a brand-new cell gets a fresh
    row marked with the saver's identity; a touched cell bumps
    ``last_modified_at`` and the ``last_modifier_*`` columns without
    overwriting the ``first_*`` history.

    Attributes:
        cell_uuid: PK + FK to :class:`NotebookCellIdentity.id`.
            Cascade-delete so a tombstoned cell loses its attribution
            row too.
        first_author_kind: ``"user"`` or ``"agent"``.
        first_author_email: Email of the human author when
            ``first_author_kind == "user"``.  ``None`` otherwise.
        first_author_agent_id: FK to :class:`Agent` when the cell was
            minted by an agent.  ``None`` for human-authored.
        first_author_agent_run_id: ``agent_runs.id`` snapshot — the
            run context the agent was in when it minted the cell.
            Surfaces in the Phase 103 replay surface.
        last_modifier_kind: Same shape as ``first_author_kind`` —
            tracks the most recent edit author.
        last_modifier_email: As ``first_author_email``.
        last_modifier_agent_id: As ``first_author_agent_id``.
        created_at: When the cell first appeared.
        last_modified_at: When the cell source last changed.
    """

    __tablename__ = "notebook_cell_authorship"

    __table_args__ = (
        Index("ix_cell_authorship_first_agent", "first_author_agent_id"),
        Index("ix_cell_authorship_last_agent", "last_modifier_agent_id"),
    )

    cell_uuid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebook_cells.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_author_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    first_author_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    first_author_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agents.id"), nullable=True
    )
    first_author_agent_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_modifier_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    last_modifier_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    last_modifier_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agents.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
