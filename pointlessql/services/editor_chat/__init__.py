"""Editor-chat services (Phase 91, renamed from ``sql_chat`` ).

The package is built in three layers:

* :mod:`_broker` — process-local pub/sub fan-out between the
  propose-route and the chat WebSocket.  No external broker (the
  chat-server is the same FastAPI process as the editor backend).
* :mod:`_session` — load-or-create / append-messages / reset for
  :class:`EditorChatSession` rows.
* :mod:`_turn` + :mod:`_agent_factory` — invocation of the
  in-process ``hermes_agent.AIAgent`` and the bridge between its
  sync streaming callback and the WS-send-queue.

All three layers are surface-agnostic; both the SQL-editor chat
 and the notebook-editor AI assistant import
from this package.  Only the propose-route fan-out helper
``publish_proposal_created`` is SQL-specific — notebook chat uses
its own ``publish_cell_proposal_created`` helper inside the new
``notebook_chat_routes`` package.
"""

from __future__ import annotations

from pointlessql.services.editor_chat._broker import (
    ChatEvent,
    publish,
    publish_cell_proposal_created,
    publish_proposal_created,
    subscribe,
    unsubscribe,
)
from pointlessql.services.editor_chat._session import (
    append_turn_messages,
    claim_turn,
    load_or_create_session,
    release_turn,
    reset_session,
)
from pointlessql.services.editor_chat._turn import (
    StreamCancelled,
    TurnResult,
    run_turn,
)

__all__ = [
    "ChatEvent",
    "StreamCancelled",
    "TurnResult",
    "append_turn_messages",
    "claim_turn",
    "load_or_create_session",
    "publish",
    "publish_cell_proposal_created",
    "publish_proposal_created",
    "release_turn",
    "reset_session",
    "run_turn",
    "subscribe",
    "unsubscribe",
]
