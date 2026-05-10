"""Lens message — one user / assistant / tool turn in a session.

Three role variants share the same row shape so the chat-loop can
serialise the whole thread back into the LLM provider format with one
linear scan.  Tool-call rows carry the structured ``tool_name`` /
``tool_args`` / ``tool_result`` payload; assistant rows carry plain
``content``; user rows carry plain ``content``.

Token + cost columns are populated for assistant turns (LLM-call cost)
and tool turns (EXPLAIN-cost for SQL-querying tools).  User turns leave
both at zero.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

VALID_ROLES: tuple[str, ...] = ("user", "assistant", "tool")
"""Allowed values for :attr:`LensMessage.role`.

Mirrored to a CHECK constraint in the lens_tables migration.  Adding a
role: bump both this tuple AND the CHECK constraint via Alembic.
"""

VALID_TOOL_STATUSES: tuple[str, ...] = (
    "ok",
    "error",
    "cost_denied",
    "session_budget_exceeded",
    "non_select_blocked",
    "workspace_isolation_blocked",
)
"""Allowed :attr:`LensMessage.tool_status` values.

Stored as plain text (no CHECK constraint) so future tool-error shapes
do not require an Alembic migration; consumer paths default-handle
unknown values as ``error``.
"""


class LensMessage(Base):
    """One message turn within a :class:`LensSession`.

    Attributes:
        id: Auto-incremented primary key.
        session_id: Owning :class:`LensSession`.  Cascade delete keeps
            the table free of orphan rows when an admin nukes a
            session.
        role: One of :data:`VALID_ROLES` — ``user`` for analyst input,
            ``assistant`` for LLM completions (final or streamed
            partial flushed to disk), ``tool`` for tool-call audit
            rows.
        content: For ``user`` / ``assistant``: the message text.  For
            ``tool``: a short human label (e.g. "Called provenance");
            the structured payload lives in ``tool_args`` /
            ``tool_result``.
        tool_name: Set on ``tool`` rows only — the registered tool
            name from :mod:`pointlessql.services.lens.tools`.
        tool_args: Set on ``tool`` rows only — the JSON-serialised
            input payload as the LLM sent it.
        tool_result: Set on ``tool`` rows only — the JSON-serialised
            output payload.  May be truncated for large rows; the
            full result lives in ``query_history`` for SQL-querying
            tools.
        tool_status: Set on ``tool`` rows only — one of
            :data:`VALID_TOOL_STATUSES`.  ``ok`` on success;
            error variants signal cost-gate denial, session-budget
            exhaustion, etc.
        tokens_in: LLM input tokens for this turn (assistant rows
            only; tool + user rows leave 0).
        tokens_out: LLM output tokens for this turn.
        cost_estimate: USD-ish estimate.  Sum across the session
            equals ``LensSession.total_cost_estimate``.
        duration_ms: Tool execution wall-clock for ``tool`` rows;
            LLM round-trip for ``assistant`` rows.  Null on user
            rows.
        created_at: Wall-clock at row insert.  Index orders the
            session's transcript chronologically.
    """

    __tablename__ = "lens_messages"
    __table_args__ = (
        Index("ix_lens_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lens_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args: Mapped[object | None] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[object | None] = mapped_column(JSON, nullable=True)
    tool_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
