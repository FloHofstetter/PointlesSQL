"""WebSocket route ``/ws/notebook/chat/{editor_session_id}``.

Notebook-editor twin of :mod:`sql_chat_ws`, built on the shared
engine in :mod:`pointlessql.api._editor_chat_ws` (same JSON-RPC
envelope).  The differences are:

* ``surface="notebook"`` is forwarded to the agent factory so the
  plugin registers ``pql_propose_cell`` / ``pql_fix_cell`` /
  ``pql_explain_cell`` instead of ``pql_propose_sql``.
* The ``refine`` method is dropped — the notebook surface has no
  "previous SQL returned 0 rows" analog; kernel errors flow back
  through the kernel WS and the user re-prompts the chat directly.
* Notify ``cell_proposal_created`` carries the polymorphic
  proposal payload (action + cell_type + target_cell_uuid + …)
  instead of the SQL-specific ``proposal_created`` shape.

``check_llm_configured`` stays a module-level global here on
purpose: tests monkeypatch
``pointlessql.api.notebook_chat_ws.check_llm_configured``, and the
route function forwards the global per connection so the patch is
honored.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from pointlessql.api._editor_chat_ws import run_chat_session
from pointlessql.services.editor_chat._agent_factory import check_llm_configured

router = APIRouter(tags=["notebook-chat-ws"])


@router.websocket("/ws/notebook/chat/{editor_session_id}")
async def notebook_chat_ws(websocket: WebSocket, editor_session_id: str) -> None:
    """Drive one notebook-chat session over a single WebSocket.

    Args:
        websocket: The incoming connection.  ``?notebook_id=…`` is
            an optional query parameter — when present, the
            agent-presence plugin tool fires from the in-process
            agent runs because the agent factory stamps
            ``POINTLESSQL_NOTEBOOK_ID`` for the plugin to read.
        editor_session_id: UUID7 minted server-side at notebook-
            editor page render and stored in ``sessionStorage`` so
            browser reload re-attaches to the same agent run.
    """
    notebook_id_raw = websocket.query_params.get("notebook_id")
    notebook_id = (
        notebook_id_raw.strip()
        if isinstance(notebook_id_raw, str) and notebook_id_raw.strip()
        else None
    )
    # ``check_llm_configured`` is resolved from this module's globals
    # at call time so a monkeypatched module attribute is forwarded.
    await run_chat_session(
        websocket,
        editor_session_id,
        surface="notebook",
        notebook_id=notebook_id,
        llm_gate=check_llm_configured,
    )


__all__ = ["router"]
