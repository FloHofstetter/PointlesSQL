"""ORM model for SQL-editor chat sessions (Phase 91).

One row per (editor-tab, user) pair that opens the chat drawer.
A chat-session is a thin wrapper around a single agent_run: the
chat owns the run for the duration of the session, every plugin
tool-call lands an operation row against that run, and the
Phase-90 ``/memory/<agent-id>`` page renders the whole
conversation trace as a memory timeline.

Conversation history is stored verbatim as the JSON message list
``hermes_agent`` consumes between turns (``role`` / ``content`` /
``tool_calls``).  The server is authoritative; WS reconnects
re-read this column and the client restores its DOM from it.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class EditorChatSession(Base):
    """A single chat-drawer session bound to one editor tab.

    Created lazily on the first WS open for a given
    ``editor_session_id`` (UUID7 generated server-side at SQL-
    editor page-render and persisted in the browser's
    ``sessionStorage`` for the tab's lifetime).  Each session owns
    exactly one ``agent_run`` row; the LLM's tool-calls and the
    human's accept-clicks both stamp operation rows against that
    run, so Phase-90 memory automatically surfaces the trace.

    Attributes:
        id: Auto-incremented primary key.
        editor_session_id: UUID7 string, unique across all chats.
            Generated server-side at editor page render so the
            client never has to negotiate it.
        workspace_id: Workspace the session lives in.
            Denormalised from the owning user's active workspace
            at session-create time.
        user_id: FK to :class:`User` — the human who owns this
            chat.  Authorisation re-checks this on every WS frame.
        agent_run_id: 1:1 FK to :class:`AgentRun`.  The chat owns
            the run for its full lifetime; closing the chat
            transitions the run to ``"succeeded"`` /
            ``"abandoned"``.
        conversation_json: JSON-encoded list of role/content
            (and optional ``tool_calls``) dicts in the shape
            ``hermes_agent.AIAgent.run_conversation`` expects as
            ``conversation_history``.  Server-authoritative;
            never read from client.
        turn_count: Monotonic counter of completed turns.
            Used to enforce ``max_turns_per_session`` from
            settings.
        current_turn_id: When non-NULL, an in-flight turn is
            running and a second WS connection should queue or
            warn rather than start a parallel turn.  Cleared on
            turn completion / cancel.
        created_at: Wall-clock instant the session was opened.
        last_active_at: Wall-clock of the last server-observed
            activity (any WS frame or REST call).  Used by a
            future GC sweep to retire stale rows.
    """

    __tablename__ = "editor_chat_sessions"
    __table_args__ = (
        Index(
            "ix_editor_chat_sessions_user_active",
            "user_id",
            "last_active_at",
        ),
        Index(
            "ix_editor_chat_sessions_workspace_active",
            "workspace_id",
            "last_active_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    editor_session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id"),
        nullable=False,
        unique=True,
    )
    conversation_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="[]"
    )
    turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    current_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_active_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
