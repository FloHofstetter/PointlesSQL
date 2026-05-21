"""Multi-cell AI proposal — full code-gen flow (Phase 104).

Extends the Phase-96 single-cell propose / fix / explain proposals
to a full sequence the user can insert as an atomic block.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookCellSequenceProposal(Base):
    """Multi-cell AI proposal — full code-gen flow (Phase 104).

    Extends the Phase-96 single-cell propose / fix / explain proposals
    to a full sequence: one prompt yields a coherent ``imports →
    DataFrame → plot → markdown`` sequence the user can insert as a
    block.  Each row carries the full cell list as JSON so insertion
    is atomic (no partial accept-then-discard pollution) and the
    reviewer-per-cell flow from Phase 101 can fan out comments to
    each cell individually after acceptance.

    Lifecycle: ``pending`` → ``accepted`` | ``discarded`` |
    ``expired``.  An accepted row fans out to N
    :class:`NotebookCellProvenance` rows once the save-path
    reconciler mints UUIDs for the freshly inserted cells.

    Attributes:
        id: Auto-incremented primary key.
        proposal_id: 36-char stable UUID for REST URLs.
        chat_session_id: FK to :class:`EditorChatSession` — the
            originating turn lives in the chat session.
        prompt: Verbatim user prompt that produced the sequence.
        cells_json: JSON list ``[{position, cell_type, source,
            result_var, tags}, …]`` — the inserted order is
            ``position`` ascending.
        rationale: Optional model-side narrative for the suggestion.
        status: One of :data:`NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES`.
        created_at: Wall-clock at proposal insertion.
        accepted_at: Set when the user accepts.
        accepted_by_user_id: Audit pointer.
        discarded_at: Set when the user discards.
    """

    __tablename__ = "notebook_cell_sequence_proposals"

    __table_args__ = (
        UniqueConstraint(
            "proposal_id", name="uq_nb_cell_sequence_proposal_uuid"
        ),
        Index(
            "ix_nb_cell_sequence_session",
            "chat_session_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("editor_chat_sessions.id"),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cells_json: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    discarded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


#: Allowed values for :attr:`NotebookCellSequenceProposal.status`.
NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "discarded",
    "expired",
)
