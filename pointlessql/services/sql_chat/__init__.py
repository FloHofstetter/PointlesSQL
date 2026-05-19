"""SQL-editor chat services (Phase 91).

The package is built in three layers:

* :mod:`_broker` — process-local pub/sub fan-out between the
  propose-route and the chat WebSocket.  No external broker (the
  chat-server is the same FastAPI process as the editor backend).
* :mod:`_session` — load-or-create / append-messages / reset for
  :class:`EditorChatSession` rows.
* :mod:`_turn` + :mod:`_agent_factory` — invocation of the
  in-process ``hermes_agent.AIAgent`` and the bridge between its
  sync streaming callback and the WS-send-queue.

Only the broker is needed before the WS route lands (Day 4); the
propose route uses :func:`publish_proposal_created` so the WS-side
can subscribe later without changing the route signature.
"""

from __future__ import annotations

from pointlessql.services.sql_chat._broker import (
    ChatEvent,
    publish,
    publish_proposal_created,
    subscribe,
    unsubscribe,
)
from pointlessql.services.sql_chat._session import (
    append_turn_messages,
    claim_turn,
    load_or_create_session,
    release_turn,
    reset_session,
)
from pointlessql.services.sql_chat._turn import (
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
    "publish_proposal_created",
    "release_turn",
    "reset_session",
    "run_turn",
    "subscribe",
    "unsubscribe",
]
