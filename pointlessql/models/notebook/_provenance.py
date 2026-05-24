"""AI-assistant cell provenance audit log.

Append-only chain that records every accepted cell proposal once the
user saves the notebook and the cell-reconciliation pass mints the
final ``cell_uuid``.
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


class NotebookCellProvenance(Base):
    """Append-only audit row for AI-assistant cell changes.

    Every accepted :class:`NotebookCellProposal` writes one row here
    once the user saves the notebook and the cell-reconciliation
    pass has minted the final ``cell_uuid``.  The table is *strictly
    append-only* — never updated, never deleted (a tombstone on the
    cell identity row implicitly tombstones the chain too).  This is
    the shape Phase 97's revision-history sprint reads to render
    "proposed by agent A at T1; fixed by agent B at T2".

    Why a separate table, not columns on
    :class:`NotebookCellIdentity`:

    * Identity is mutable (``current_content_hash`` /
      ``ordinal_hint`` change on every save).  Mutating identity
      columns would lose the chain.
    * One cell can accumulate many provenance rows (initial propose
      + N subsequent fixes + M explanations).  Cardinality belongs
      in a child table, not a single-row column.

    Attributes:
        id: Auto-incremented primary key.
        cell_uuid: FK to :class:`NotebookCellIdentity.id` — the
            stable cell identity the proposal landed on.
        agent_run_id: FK to :class:`AgentRun` — the agent run that
            authored the proposal.  Equal to the chat session's
            ``agent_run_id`` for chat-driven proposals.
        proposal_id: FK to
            :class:`NotebookCellProposal.proposal_id` — the
            originating draft, so the audit trail can look up
            ``rationale`` / ``new_source`` if needed.
        action: ``"propose"`` | ``"fix"`` | ``"explain"`` —
            mirrors the proposal's action.
        created_at: Wall-clock of provenance write (i.e. when the
            user saved the notebook after accepting the proposal).
    """

    __tablename__ = "notebook_cell_provenance"

    __table_args__ = (
        Index(
            "ix_notebook_cell_provenance_cell",
            "cell_uuid",
            "created_at",
        ),
        Index(
            "ix_notebook_cell_provenance_run",
            "agent_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cell_uuid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebook_cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
