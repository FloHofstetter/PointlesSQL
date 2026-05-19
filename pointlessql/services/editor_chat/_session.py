"""Load-or-create / append / reset helpers for chat sessions.

Each browser tab generates an ``editor_session_id`` (UUID7) at SQL-
editor page render and persists it in ``sessionStorage``.  When the
WS opens for that id we either restore the existing
:class:`EditorChatSession` row (and its conversation history) or
create a fresh one alongside a new ``agent_run`` so every
plugin-tool call lands on the same run.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from pointlessql.models import AgentRun, EditorChatSession

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def load_or_create_session(
    session_factory: sessionmaker[Any],
    *,
    editor_session_id: str,
    user_id: int,
    user_email: str,
    workspace_id: int,
) -> tuple[int, str, list[dict[str, Any]]]:
    """Return ``(chat_session_id, agent_run_id, conversation_history)``.

    Idempotent: a second call with the same ``editor_session_id``
    returns the existing row.  Used by the WS-open path so a
    browser reload re-attaches to the same agent run instead of
    spawning a new one.

    Args:
        session_factory: SQLAlchemy session factory.
        editor_session_id: UUID7 from the browser tab.  Server-
            generated at page render, persisted in sessionStorage.
        user_id: Owning :class:`User`'s primary key.
        user_email: Stamped onto the new :class:`AgentRun` as
            ``principal`` so the audit trail shows the human even
            when the LLM signed every tool-call.
        workspace_id: Workspace scope for both the chat session
            and its agent_run.

    Returns:
        A tuple ``(chat_session_id, agent_run_id, history)`` where
        ``history`` is the deserialised conversation list ready to
        hand to ``AIAgent.run_conversation``.
    """
    with session_factory() as session:
        existing = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .one_or_none()
        )
        if existing is not None:
            existing.last_active_at = datetime.datetime.now(datetime.UTC)
            session.commit()
            history_raw = json.loads(existing.conversation_json)
            history = _coerce_history(history_raw)
            return existing.id, existing.agent_run_id, history

        now = datetime.datetime.now(datetime.UTC)
        agent_run_id = str(uuid.uuid4())
        session.add(
            AgentRun(
                id=agent_run_id,
                workspace_id=workspace_id,
                principal=user_email,
                agent_id=f"sql-chat-{editor_session_id[:8]}",
                notebook_path=f"/internal/sql-chat/{editor_session_id}",
                status="running",
                started_at=now,
            )
        )
        chat_session = EditorChatSession(
            editor_session_id=editor_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            agent_run_id=agent_run_id,
            conversation_json="[]",
            turn_count=0,
            created_at=now,
            last_active_at=now,
        )
        session.add(chat_session)
        session.commit()
        return chat_session.id, agent_run_id, []


def append_turn_messages(
    session_factory: sessionmaker[Any],
    *,
    chat_session_id: int,
    new_messages: Sequence[dict[str, Any]],
) -> int:
    """Append *new_messages* to the stored conversation; bump turn count.

    Args:
        session_factory: SQLAlchemy session factory.
        chat_session_id: PK of the :class:`EditorChatSession` row.
        new_messages: List of role/content (and optional
            ``tool_calls``) dicts produced by the last
            ``AIAgent.run_conversation`` turn.  We append, not
            replace, so the full multi-turn trace stays in the JSON.

    Returns:
        The new turn count after the append.

    Raises:
        ValueError: When ``chat_session_id`` is not a known session
            (the row has been deleted while a turn was in flight).
    """
    with session_factory() as session:
        row = session.get(EditorChatSession, chat_session_id)
        if row is None:
            msg = f"chat session {chat_session_id} not found"
            raise ValueError(msg)
        history_raw = json.loads(row.conversation_json)
        history = _coerce_history(history_raw)
        history.extend(dict(msg) for msg in new_messages)
        row.conversation_json = json.dumps(history)
        row.turn_count = row.turn_count + 1
        row.last_active_at = datetime.datetime.now(datetime.UTC)
        row.current_turn_id = None
        session.commit()
        return row.turn_count


def reset_session(
    session_factory: sessionmaker[Any],
    *,
    chat_session_id: int,
) -> None:
    """Truncate the conversation history; keep the row + agent_run."""
    with session_factory() as session:
        row = session.get(EditorChatSession, chat_session_id)
        if row is None:
            return
        row.conversation_json = "[]"
        row.turn_count = 0
        row.last_active_at = datetime.datetime.now(datetime.UTC)
        row.current_turn_id = None
        session.commit()


def claim_turn(
    session_factory: sessionmaker[Any],
    *,
    chat_session_id: int,
    turn_id: str,
) -> bool:
    """Atomically set ``current_turn_id``; return ``False`` if already set.

    Prevents two WS connections from kicking off concurrent turns
    on the same session.  The second one sees ``False`` and is
    expected to surface a "turn already running" notify to the
    client.

    Args:
        session_factory: SQLAlchemy session factory.
        chat_session_id: PK of the :class:`EditorChatSession` row.
        turn_id: Caller-generated UUID identifying the new turn.

    Returns:
        ``True`` when the claim was granted (caller may proceed),
        ``False`` when another turn is already in flight.
    """
    with session_factory() as session:
        row = session.get(EditorChatSession, chat_session_id)
        if row is None:
            return False
        if row.current_turn_id:
            return False
        row.current_turn_id = turn_id
        session.commit()
        return True


def release_turn(
    session_factory: sessionmaker[Any],
    *,
    chat_session_id: int,
) -> None:
    """Clear ``current_turn_id``; called from the turn-runner finally."""
    with session_factory() as session:
        row = session.get(EditorChatSession, chat_session_id)
        if row is None:
            return
        row.current_turn_id = None
        session.commit()


def _coerce_history(raw: Any) -> list[dict[str, Any]]:
    """Tolerate JSON shapes that aren't ``list[dict]`` (corruption guard)."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:  # type: ignore[reportUnknownVariableType]
        if isinstance(item, dict):
            result.append({str(k): v for k, v in item.items()})  # type: ignore[reportUnknownVariableType]
    return result
