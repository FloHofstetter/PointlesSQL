"""Editor-chat ORM (renamed from ``sql_chat``).

Re-exports the chat-substrate tables.  The module path is
``editor_chat`` (not ``sql_chat``) because the session table is
generic across editor surfaces — both the SQL-editor chat panel
and the notebook-editor AI assistant share it.

* :class:`EditorChatSession` — one row per (editor-tab, user) pair;
  carries the conversation history and the 1:1 ``agent_run_id``
  link.  Generic across editor surfaces.
* :class:`ChatProposal` — one row per DML/DDL SQL draft awaiting
  human review (SQL-editor only).  Lives in
  :mod:`pointlessql.models.editor_chat._sql_proposal` to make its
  SQL-specificity obvious next to the
  ``_cell_proposal.py`` notebook sibling.
"""

from __future__ import annotations

from pointlessql.models.editor_chat._cell_proposal import (
    NOTEBOOK_CELL_PROPOSAL_ACTIONS,
    NOTEBOOK_CELL_PROPOSAL_STATUSES,
    NotebookCellProposal,
)
from pointlessql.models.editor_chat._session import EditorChatSession
from pointlessql.models.editor_chat._sql_proposal import (
    CHAT_PROPOSAL_KINDS,
    CHAT_PROPOSAL_STATUSES,
    ChatProposal,
)

__all__ = [
    "CHAT_PROPOSAL_KINDS",
    "CHAT_PROPOSAL_STATUSES",
    "ChatProposal",
    "EditorChatSession",
    "NOTEBOOK_CELL_PROPOSAL_ACTIONS",
    "NOTEBOOK_CELL_PROPOSAL_STATUSES",
    "NotebookCellProposal",
]
