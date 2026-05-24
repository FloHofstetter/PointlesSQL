"""Lens chat session — one thread per user + workspace.

Each session pins to one workspace (so the analyst's data scope is
unambiguous) and one owner (so two analysts in the same workspace get
independent threads).  ``llm_provider`` + ``llm_model`` are recorded
per-session because the BYO-key flow lets a workspace switch providers
between sessions; we want the audit trail to reflect which provider
served the conversation.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class LensSession(Base):
    """One Lens chat session.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this session belongs to.  Hard
            isolation: every tool call inside the session is scoped
            to this workspace, and the analyst can not point Lens at
            a different workspace mid-session (they start a new one).
        owner_id: User who created the session.  Visibility is
            owner-only by default; admins see every session in the
            workspace.
        title: Short human label, defaults to the first user message
            (truncated) when the session is first persisted.
        llm_provider: One of :data:`LENS_PROVIDERS` — pins which BYO
            credential row the chat-loop uses.  Recorded per session
            because workspaces can swap providers between sessions.
        llm_model: Provider-specific model identifier (e.g.
            ``gpt-4o-mini`` or ``claude-haiku-4-5-20251001``).  Free
            text rather than an enum because new models ship faster
            than we can ship migrations.
        total_cost_estimate: Running sum of per-tool-call EXPLAIN cost
            estimates plus per-LLM-call token cost (USD-ish, see
            :mod:`pointlessql.services.lens.cost_gate`).  Hard cap
            from :class:`LensSettings.max_session_cost`.
        created_at: Wall-clock at session creation.
        updated_at: Wall-clock at last persisted mutation.
        last_message_at: Wall-clock at the most recent message
            append; null when the session was just created.  Used as
            the sidebar sort key.
    """

    __tablename__ = "lens_sessions"
    __table_args__ = (
        Index("ix_lens_sessions_workspace_owner", "workspace_id", "owner_id"),
        Index(
            "ix_lens_sessions_last_message",
            "workspace_id",
            "last_message_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    total_cost_estimate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_message_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
