"""ORM model for SQL-chat proposals.

When the LLM decides to issue a non-SELECT statement it must call
the ``pql_propose_sql`` plugin tool rather than ``pql_query`` — the
propose tool writes a :class:`ChatProposal` row and fans out a WS
notification that lifts the SQL into the editor as a "Draft — click
Run to execute" banner.  Acceptance routes the SQL through the
existing ``/api/sql/execute`` dispatcher with the chat session's
``agent_run_id`` so the operation hangs off the same run as every
other tool-call in the conversation.

The model is intentionally small: status transitions are linear
(``pending`` → ``accepted`` | ``discarded`` | ``expired``), the
``accepted_at`` timestamp doubles as a discard timestamp via the
``status`` column.
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

CHAT_PROPOSAL_KINDS: tuple[str, ...] = ("dml", "ddl")
"""Allowed values for :attr:`ChatProposal.kind`.

SELECT is intentionally absent: the agent must use the
``pql_query`` tool for reads (which auto-executes capped via the
existing dispatcher) and reserve ``pql_propose_sql`` for writes
that need a human's click before they run.
"""

CHAT_PROPOSAL_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "discarded",
    "expired",
)
"""Allowed values for :attr:`ChatProposal.status`.

``pending`` is the create-time default; ``accepted`` is set when
the user clicks Run and the SQL is forwarded to the dispatcher;
``discarded`` is an explicit dismiss; ``expired`` is set by the
accept-endpoint when ``created_at`` is older than 24h.
"""


class ChatProposal(Base):
    """A draft DML/DDL statement awaiting human review.

    Created by the ``pql_propose_sql`` plugin tool when the LLM
    decides to issue a non-SELECT.  Lives until the user clicks
    Run (status → ``accepted``) or Discard (status →
    ``discarded``).  Stale proposals — older than 24h — are
    rejected with 409 on accept and the accept-endpoint flips
    them to ``expired`` so the audit trail shows they were not
    silently dropped.

    Attributes:
        id: Auto-incremented primary key.
        proposal_id: UUID4 string the WS notify frame carries to
            the client; the accept/discard endpoints take it as
            their path parameter so URLs don't leak internal IDs.
        chat_session_id: FK to :class:`EditorChatSession`.  The
            proposal is scoped to the session it was drafted in;
            accept routes through that session's ``agent_run_id``.
        workspace_id: Denormalised from the parent session for
            workspace-scoped audit reads without a JOIN.
        sql_text: Verbatim SQL the agent proposed.  Never edited
            server-side — the user clicks Run or Discard; if they
            want to tweak it they paste into the editor and run
            from there (which still lands on the chat-run via the
            ``X-Agent-Run-Id`` header bridge).
        kind: ``"dml"`` (INSERT/UPDATE/DELETE/MERGE) or ``"ddl"``
            (CREATE/DROP/ALTER/TRUNCATE).  CHECK-constrained.
        rationale: Optional LLM-authored explanation of *why* this
            SQL was proposed.  Surface in the banner above the
            Run button so the human can sanity-check intent.
        status: Lifecycle state — see :data:`CHAT_PROPOSAL_STATUSES`.
        created_at: Wall-clock instant the propose-tool ran.
        accepted_at: Wall-clock instant the user clicked Run /
            Discard, or the expiry sweep flipped the row.  ``None``
            while ``status == "pending"``.
        accepted_run_id: FK to :class:`AgentRun` that executed
            the proposal.  Identical to the parent session's
            ``agent_run_id`` for chat-driven accepts; populated
            only when ``status == "accepted"``.
    """

    __tablename__ = "chat_proposals"
    __table_args__ = (
        Index("ix_chat_proposals_session", "chat_session_id", "created_at"),
        Index("ix_chat_proposals_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "kind IN ('dml', 'ddl')",
            name="ck_chat_proposals_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'discarded', 'expired')",
            name="ck_chat_proposals_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("editor_chat_sessions.id"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )
