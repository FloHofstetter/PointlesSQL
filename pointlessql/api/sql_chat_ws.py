"""WebSocket route ``/ws/sql/chat/{editor_session_id}`` (Phase 91).

Mirrors the JSON-RPC envelope from :mod:`notebook_kernel_ws`:

* Inbound frames: ``{"id": int, "method": str, "params": dict}``.
* Outbound replies: ``{"id": int, "result": dict}`` or ``{"id": int,
  "error": {"code": str, "message": str}}``.
* Outbound notifications: ``{"notify": str, "params": dict}``.

Supported methods:

* ``prompt`` — start a new turn with ``params.text``.
* ``cancel`` — set the cancel-event on the active turn.
* ``reset`` — clear the conversation history.

Auth is re-resolved per connection because Starlette HTTP
middleware does not run for WebSocket upgrades (same caveat as
the notebook kernel WS).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pointlessql.api.ws_auth import resolve_websocket_user
from pointlessql.exceptions import ValidationError
from pointlessql.services.editor_chat import (
    ChatEvent,
    append_turn_messages,
    claim_turn,
    load_or_create_session,
    publish,
    release_turn,
    reset_session,
    run_turn,
    subscribe,
    unsubscribe,
)
from pointlessql.services.editor_chat._agent_factory import (
    LLM_NOT_CONFIGURED_REASON,
    check_llm_configured,
)

if TYPE_CHECKING:
    from pointlessql.config import Settings
    from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql-chat-ws"])

_executor_singleton: ThreadPoolExecutor | None = None
_executor_lock: threading.Lock = threading.Lock()


def _get_executor(workers: int) -> ThreadPoolExecutor:
    """Return a process-singleton thread pool for AIAgent runs."""
    global _executor_singleton
    with _executor_lock:
        if _executor_singleton is None:
            _executor_singleton = ThreadPoolExecutor(
                max_workers=max(1, workers),
                thread_name_prefix="sql-chat-turn",
            )
    return _executor_singleton


@router.websocket("/ws/sql/chat/{editor_session_id}")
async def sql_chat_ws(websocket: WebSocket, editor_session_id: str) -> None:
    """Drive one chat session over a single WebSocket.

    Args:
        websocket: The incoming connection.
        editor_session_id: UUID7 from the SQL-editor page render.
    """
    settings: Settings = websocket.app.state.settings
    if not settings.editor_chat.enabled:
        await websocket.close(code=4503, reason="editor_chat_disabled")
        return
    user = resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    if not check_llm_configured():
        await websocket.close(code=1011, reason=LLM_NOT_CONFIGURED_REASON)
        return

    factory = websocket.app.state.session_factory
    workspace_id = int(getattr(websocket.state, "workspace_id", 0) or 0) or 1
    chat_session_id, agent_run_id, history = load_or_create_session(
        factory,
        editor_session_id=editor_session_id,
        user_id=int(user.get("id") or 0),
        user_email=str(user.get("email") or ""),
        workspace_id=workspace_id,
    )

    await websocket.accept()
    queue = subscribe(editor_session_id)
    cancel_event = threading.Event()
    active_turn: dict[str, Any] = {"id": None, "task": None}

    pump_task = asyncio.create_task(
        _pump_broker(websocket, queue),
        name=f"sql-chat-pump-{editor_session_id[:8]}",
    )

    await _send_notify(
        websocket,
        kind="ready",
        params={
            "agent_run_id": agent_run_id,
            "history": history,
        },
    )

    try:
        while True:
            try:
                text = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            await _handle_frame(
                websocket,
                frame_text=text,
                settings=settings,
                factory=factory,
                editor_session_id=editor_session_id,
                chat_session_id=chat_session_id,
                agent_run_id=agent_run_id,
                user=user,
                cancel_event=cancel_event,
                active_turn=active_turn,
            )
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        unsubscribe(editor_session_id, queue)


async def _pump_broker(
    websocket: WebSocket,
    queue: asyncio.Queue[ChatEvent],
) -> None:
    """Forward every :class:`ChatEvent` to the WS as a notify frame."""
    while True:
        event = await queue.get()
        await _send_notify(
            websocket,
            kind=event.kind,
            params=event.payload,
        )


async def _handle_frame(
    websocket: WebSocket,
    *,
    frame_text: str,
    settings: Settings,
    factory: Any,
    editor_session_id: str,
    chat_session_id: int,
    agent_run_id: str,
    user: UserInfo,  # noqa: ARG001
    cancel_event: threading.Event,
    active_turn: dict[str, Any],
) -> None:
    """Parse one inbound frame and route to the matching handler."""
    try:
        frame_any: Any = json.loads(frame_text)
    except json.JSONDecodeError:
        await _send_error(websocket, request_id=None, code="bad_json", message="frame not JSON")
        return
    if not isinstance(frame_any, dict):
        await _send_error(
            websocket, request_id=None, code="bad_frame", message="frame must be a JSON object"
        )
        return
    frame: dict[str, Any] = {str(k): v for k, v in frame_any.items()}  # type: ignore[reportUnknownVariableType]
    request_id_raw = frame.get("id")
    request_id: int | None = (
        request_id_raw if isinstance(request_id_raw, int) else None
    )
    method_raw = frame.get("method")
    method: str | None = method_raw if isinstance(method_raw, str) else None
    params_raw = frame.get("params")
    params: dict[str, Any] = (
        {str(k): v for k, v in params_raw.items()}  # type: ignore[reportUnknownVariableType]
        if isinstance(params_raw, dict)
        else {}
    )

    if method == "prompt":
        await _handle_prompt(
            websocket,
            request_id=request_id,
            params=params,
            settings=settings,
            factory=factory,
            editor_session_id=editor_session_id,
            chat_session_id=chat_session_id,
            agent_run_id=agent_run_id,
            cancel_event=cancel_event,
            active_turn=active_turn,
        )
    elif method == "refine":
        refine_text = _format_refine_hint(params)
        if refine_text is None:
            await _send_error(
                websocket,
                request_id=request_id,
                code="bad_refine",
                message="params.hint must be 'zero_rows' or 'error'",
            )
            return
        await _handle_prompt(
            websocket,
            request_id=request_id,
            params={"text": refine_text},
            settings=settings,
            factory=factory,
            editor_session_id=editor_session_id,
            chat_session_id=chat_session_id,
            agent_run_id=agent_run_id,
            cancel_event=cancel_event,
            active_turn=active_turn,
        )
    elif method == "cancel":
        cancel_event.set()
        await _send_reply(
            websocket, request_id=request_id, result={"cancelled": True}
        )
    elif method == "reset":
        reset_session(factory, chat_session_id=chat_session_id)
        await _send_reply(
            websocket, request_id=request_id, result={"reset": True}
        )
    else:
        await _send_error(
            websocket,
            request_id=request_id,
            code="unknown_method",
            message=f"unknown method: {method!r}",
        )


async def _handle_prompt(
    websocket: WebSocket,
    *,
    request_id: int | None,
    params: dict[str, Any],
    settings: Settings,
    factory: Any,
    editor_session_id: str,
    chat_session_id: int,
    agent_run_id: str,
    cancel_event: threading.Event,
    active_turn: dict[str, Any],
) -> None:
    """Validate prompt input, claim the turn, and run it on the executor."""
    text = params.get("text")
    if not isinstance(text, str) or not text.strip():
        await _send_error(
            websocket,
            request_id=request_id,
            code="bad_prompt",
            message="params.text is required",
        )
        return
    if active_turn["id"] is not None:
        await _send_error(
            websocket,
            request_id=request_id,
            code="turn_in_flight",
            message="another turn is already running; cancel it first",
        )
        return
    turn_id = str(uuid.uuid4())
    if not claim_turn(factory, chat_session_id=chat_session_id, turn_id=turn_id):
        await _send_error(
            websocket,
            request_id=request_id,
            code="turn_in_flight",
            message="another connection holds an active turn",
        )
        return

    cancel_event.clear()
    active_turn["id"] = turn_id
    await _send_reply(
        websocket,
        request_id=request_id,
        result={"turn_id": turn_id, "agent_run_id": agent_run_id},
    )

    async def _runner() -> None:
        try:
            history = _reload_history(factory, chat_session_id)
            executor = _get_executor(settings.editor_chat.executor_workers)
            try:
                result = await run_turn(
                    settings=settings,
                    executor=executor,
                    editor_session_id=editor_session_id,
                    agent_run_id=agent_run_id,
                    user_message=text,
                    conversation_history=history,
                    cancel_event=cancel_event,
                )
            except ValidationError as exc:
                publish(
                    editor_session_id,
                    ChatEvent(kind="error", payload={"detail": str(exc)}),
                )
                return
            except Exception as exc:  # noqa: BLE001 — bubble to client
                logger.exception("chat turn failed")
                publish(
                    editor_session_id,
                    ChatEvent(kind="error", payload={"detail": str(exc)}),
                )
                return
            # Yield to the loop so any pending call_soon_threadsafe
            # callbacks (token publishes from the executor) drain before
            # we enqueue the terminal frame.  Without this, the
            # future-resolution continuation that brought us here can
            # outrun the publish callbacks in the ready queue and the
            # client sees ``final`` before any ``token`` frame.
            await asyncio.sleep(0)
            if result.cancelled:
                publish(
                    editor_session_id,
                    ChatEvent(
                        kind="cancelled", payload={"turn_id": turn_id}
                    ),
                )
            else:
                appended = [
                    {"role": "user", "content": text},
                    *result.messages,
                ]
                append_turn_messages(
                    factory,
                    chat_session_id=chat_session_id,
                    new_messages=appended,
                )
                publish(
                    editor_session_id,
                    ChatEvent(
                        kind="final",
                        payload={
                            "text": result.final_response,
                            "api_calls": result.api_calls,
                            "turn_id": turn_id,
                        },
                    ),
                )
        finally:
            release_turn(factory, chat_session_id=chat_session_id)
            active_turn["id"] = None
            active_turn["task"] = None

    active_turn["task"] = asyncio.create_task(
        _runner(),
        name=f"sql-chat-turn-{turn_id[:8]}",
    )


def _reload_history(factory: Any, chat_session_id: int) -> list[dict[str, Any]]:
    """Re-read conversation_json so the turn sees the latest committed state."""
    from pointlessql.models import EditorChatSession

    with factory() as session:
        row = session.get(EditorChatSession, chat_session_id)
        if row is None:
            return []
        raw = json.loads(row.conversation_json)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]  # type: ignore[reportUnknownVariableType]


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


async def _send_notify(websocket: WebSocket, *, kind: str, params: dict[str, Any]) -> None:
    """Send a ``{"notify": kind, "params": params}`` frame."""
    await websocket.send_text(
        json.dumps({"notify": kind, "params": params})
    )


async def _send_reply(
    websocket: WebSocket,
    *,
    request_id: int | None,
    result: dict[str, Any],
) -> None:
    """Send a ``{"id": request_id, "result": ...}`` frame."""
    if request_id is None:
        return
    await websocket.send_text(json.dumps({"id": request_id, "result": result}))


async def _send_error(
    websocket: WebSocket,
    *,
    request_id: int | None,
    code: str,
    message: str,
) -> None:
    """Send a ``{"id": ..., "error": {"code": ..., "message": ...}}`` frame."""
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id is not None:
        body["id"] = request_id
    await websocket.send_text(json.dumps(body))


__all__ = ["router"]
