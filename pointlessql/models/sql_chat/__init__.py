"""SQL-editor chat-session ORM (Phase 91).

Re-exports the two tables that back the NL→SQL chat panel:

* :class:`EditorChatSession` — one row per (editor-tab, user)
  pair; carries the conversation history and the 1:1
  ``agent_run_id`` link.
* :class:`ChatProposal` — one row per DML/DDL draft awaiting
  human review.
"""

from __future__ import annotations

from pointlessql.models.sql_chat._proposal import (
    CHAT_PROPOSAL_KINDS,
    CHAT_PROPOSAL_STATUSES,
    ChatProposal,
)
from pointlessql.models.sql_chat._session import EditorChatSession

__all__ = [
    "CHAT_PROPOSAL_KINDS",
    "CHAT_PROPOSAL_STATUSES",
    "ChatProposal",
    "EditorChatSession",
]
