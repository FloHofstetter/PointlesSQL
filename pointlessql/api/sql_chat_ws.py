"""WebSocket route ``/ws/sql/chat/{editor_session_id}``.

Thin wrapper over the shared engine in
:mod:`pointlessql.api._editor_chat_ws`, which documents the JSON-RPC
envelope and the ``prompt`` / ``cancel`` / ``reset`` methods.  The
SQL surface adds one method of its own:

* ``refine`` — templates the human's "this didn't work, try again"
  affordance (``params.hint`` of ``zero_rows`` or ``error``) into a
  structured user prompt and runs it through the normal turn
  pipeline.

``check_llm_configured`` stays a module-level global here on
purpose: tests monkeypatch
``pointlessql.api.sql_chat_ws.check_llm_configured``, and the route
function forwards the global per connection so the patch is honored.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket

from pointlessql.api._editor_chat_ws import run_chat_session
from pointlessql.api._ws_error import send_error as _send_error
from pointlessql.services.editor_chat._agent_factory import check_llm_configured

if TYPE_CHECKING:
    from pointlessql.api._editor_chat_ws import PromptRunner

router = APIRouter(tags=["sql-chat-ws"])


@router.websocket("/ws/sql/chat/{editor_session_id}")
async def sql_chat_ws(websocket: WebSocket, editor_session_id: str) -> None:
    """Drive one chat session over a single WebSocket.

    Args:
        websocket: The incoming connection.
        editor_session_id: UUID7 from the SQL-editor page render.
    """
    # ``check_llm_configured`` is resolved from this module's globals
    # at call time so a monkeypatched module attribute is forwarded.
    await run_chat_session(
        websocket,
        editor_session_id,
        surface="sql",
        llm_gate=check_llm_configured,
        extra_frame_handler=_handle_refine_frame,
    )


async def _handle_refine_frame(
    websocket: WebSocket,
    request_id: int | None,
    method: str | None,
    params: dict[str, Any],
    run_prompt: PromptRunner,
) -> bool:
    """Handle the SQL-only ``refine`` method.

    Args:
        websocket: The accepted connection (for error envelopes).
        request_id: Echoed back on the reply or error frame.
        method: The inbound frame's method name.
        params: The inbound frame's params object.
        run_prompt: Engine callback that runs the synthesized prompt
            through the normal turn pipeline.

    Returns:
        ``True`` when the frame was a ``refine`` request (handled,
        successfully or with a ``bad_refine`` error envelope);
        ``False`` to fall through to the engine's unknown-method
        error.
    """
    if method != "refine":
        return False
    refine_text = _format_refine_hint(params)
    if refine_text is None:
        await _send_error(
            websocket,
            request_id=request_id,
            code="bad_refine",
            message="params.hint must be 'zero_rows' or 'error'",
        )
        return True
    await run_prompt(request_id, {"text": refine_text})
    return True


def _format_refine_hint(params: dict[str, Any]) -> str | None:
    """Build the templated refine prompt from the client's hint payload.

    Two canonical stencils:

    * ``zero_rows`` — the prior tool result returned no rows.
    * ``error`` — the prior tool result raised; ``last_error`` is
      appended verbatim so the LLM can see the failure mode.

    Returns ``None`` when ``hint`` is unrecognised so the WS layer
    can surface a 4xx-style envelope back to the client.

    Args:
        params: The ``params`` dict from the inbound refine frame.

    Returns:
        A stencil-rendered prompt string, or ``None`` when the
        hint is invalid.
    """
    hint = params.get("hint")
    last_sql = params.get("last_sql") or ""
    if not isinstance(hint, str):
        return None
    if hint == "zero_rows":
        return (
            "Refine: the previous SQL\n\n"
            f"```sql\n{last_sql}\n```\n\n"
            "returned 0 rows.  Possible causes: filter too narrow, "
            "wrong join condition, or a NULL-handling oversight.  "
            "Please rewrite to widen the filter or fix the join, then "
            "explain what you changed."
        )
    if hint == "error":
        last_error = params.get("last_error") or "(no error detail)"
        return (
            "Refine: the previous SQL\n\n"
            f"```sql\n{last_sql}\n```\n\n"
            f"failed with:\n\n```\n{last_error}\n```\n\n"
            "Please rewrite to fix the error and explain what you changed."
        )
    return None


__all__ = ["router"]
