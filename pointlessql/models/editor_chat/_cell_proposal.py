"""ORM model for notebook cell proposals (Phase 96).

When the notebook-editor AI assistant proposes a change to a
notebook cell, the plugin tool POSTs to ``/api/notebook/chat/{id}/...``
and the route writes a :class:`NotebookCellProposal` row + fans
out a broker event.  The user reviews the draft as a banner in the
chat drawer and clicks Insert (propose) / Apply (fix) / Discard.

The model is polymorphic across three actions:

* ``propose`` — insert a brand-new cell (``cell_type`` + ``new_source``,
  optional ``position_after_cell_uuid`` / ``position_at_end``).
* ``fix`` — replace an existing cell's source (``target_cell_uuid``
  + ``new_source``).  Idempotency window of 60 s prevents agent
  retries from flooding the editor.
* ``explain`` — attach an explanation to an existing cell
  (``target_cell_uuid`` + ``explanation``).  Created with
  ``status='accepted'`` directly — no Run button; the explanation
  is rendered in the per-cell social drawer's "Explanations" tab.

Status transitions are linear (``pending`` → ``accepted`` /
``discarded`` / ``expired``).  Provenance — which agent run the
proposal came from and which final ``cell_uuid`` it landed on —
is captured in the separate append-only :class:`NotebookCellProvenance`
table the save-route writes after reconciliation runs.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

NOTEBOOK_CELL_PROPOSAL_ACTIONS: tuple[str, ...] = (
    "propose",
    "fix",
    "explain",
)
"""Allowed values for :attr:`NotebookCellProposal.action`.

* ``propose`` — insert a new cell (``cell_type`` + ``new_source``).
* ``fix`` — replace ``target_cell_uuid``'s source with ``new_source``.
* ``explain`` — attach ``explanation`` to ``target_cell_uuid``.
"""

NOTEBOOK_CELL_PROPOSAL_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "discarded",
    "expired",
)
"""Allowed values for :attr:`NotebookCellProposal.status`.

``pending`` is the create-time default for ``propose`` and ``fix``.
``explain`` is created directly as ``accepted`` (no Run button).
``expired`` is set on accept if the proposal is older than 24 h.
"""


class NotebookCellProposal(Base):
    """A pending / accepted notebook-cell draft from the AI assistant.

    Attributes:
        id: Auto-incremented primary key.
        proposal_id: UUID4 string the WS notify frame carries to
            the client; the accept/discard endpoints take it as
            their path parameter so URLs don't leak internal IDs.
        chat_session_id: FK to :class:`EditorChatSession`.  The
            proposal is scoped to the chat session that drafted it.
        workspace_id: Denormalised from the parent session for
            workspace-scoped audit reads without a JOIN.
        action: ``"propose"`` | ``"fix"`` | ``"explain"``.
        cell_type: ``"code"`` or ``"markdown"`` for propose;
            ``None`` for fix + explain.
        target_cell_uuid: FK-style reference to the existing
            :class:`NotebookCellIdentity` row the action targets.
            Required for fix + explain; ``None`` for propose
            (the inserted cell's UUID is recorded in
            ``inserted_cell_uuid`` once the save-path reconciler
            mints it).
        new_source: Verbatim cell source the agent proposes.
            Required for propose + fix; ``None`` for explain.
        explanation: Free-text explanation attached to the cell.
            Required for explain; ``None`` for propose + fix.
        position_after_cell_uuid: For propose: insert after this
            existing cell's UUID.  ``None`` means use
            ``position_at_end`` (or default to end if both unset).
        position_at_end: For propose: append at the end of the
            notebook.  Boolean default ``False``.
        rationale: Optional one-paragraph LLM-authored explanation
            of *why* this change was proposed.  Rendered in the
            banner above Insert / Apply / Discard.
        status: Lifecycle state — see
            :data:`NOTEBOOK_CELL_PROPOSAL_STATUSES`.
        created_at: Wall-clock instant the propose-route ran.
        accepted_at: Wall-clock the user clicked Insert / Apply /
            Discard, or the expiry sweep flipped the row.  Equal to
            ``created_at`` for ``explain`` (auto-accept).
        accepted_run_id: FK to :class:`AgentRun` whose tool-call
            authored this proposal.  Identical to the chat
            session's ``agent_run_id``; surfaced here so the audit
            query doesn't have to JOIN through the chat session.
        inserted_cell_uuid: Final ``cell_uuid`` the save-path
            reconciler assigned to the new cell (propose only) or
            the unchanged ``target_cell_uuid`` (fix + explain).
            Populated when the user saves the notebook after
            accepting; ``None`` while still un-saved.
    """

    __tablename__ = "notebook_cell_proposals"
    __table_args__ = (
        Index(
            "ix_notebook_cell_proposals_session",
            "chat_session_id",
            "created_at",
        ),
        Index(
            "ix_notebook_cell_proposals_workspace_status",
            "workspace_id",
            "status",
        ),
        # Block two pending fixes against the same cell at once so
        # the user doesn't see a stack of duplicate banners.
        Index(
            "ux_notebook_cell_proposals_pending_fix",
            "chat_session_id",
            "action",
            "target_cell_uuid",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
        CheckConstraint(
            "action IN ('propose', 'fix', 'explain')",
            name="ck_notebook_cell_proposals_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'discarded', 'expired')",
            name="ck_notebook_cell_proposals_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True
    )
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("editor_chat_sessions.id"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    cell_type: Mapped[str | None] = mapped_column(String(12), nullable=True)
    target_cell_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    new_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_after_cell_uuid: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    position_at_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )
    inserted_cell_uuid: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
