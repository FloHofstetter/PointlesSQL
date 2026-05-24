"""WebSocket route ``/ws/notebook/chat/{editor_session_id}`` (Phase 96).

Notebook-editor twin of :mod:`sql_chat_ws` (Phase 91).  Same
JSON-RPC envelope; the differences are:

* ``surface="notebook"`` is forwarded to the agent factory so the
  plugin registers ``pql_propose_cell`` / ``pql_fix_cell`` /
  ``pql_explain_cell`` instead of ``pql_propose_sql``.
* The ``refine`` method is dropped — the notebook surface has no
  "previous SQL returned 0 rows" analog; kernel errors flow back
  through the kernel WS and the user re-prompts the chat directly.
* Notify ``cell_proposal_created`` carries the polymorphic
  proposal payload (action + cell_type + target_cell_uuid + …)
  instead of the SQL-specific ``proposal_created`` shape.

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

from pointlessql.api._ws_error import send_error as _send_error
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebook-chat-ws"])

_executor_singleton: ThreadPoolExecutor | None = None
_executor_lock: threading.Lock = threading.Lock()


def _get_executor(workers: int) -> ThreadPoolExecutor:
    """Return a process-singleton thread pool for AIAgent runs."""
    global _executor_singleton
    with _executor_lock:
        if _executor_singleton is None:
            _executor_singleton = ThreadPoolExecutor(
                max_workers=max(1, workers),
                thread_name_prefix="notebook-chat-turn",
            )
    return _executor_singleton


@router.websocket("/ws/notebook/chat/{editor_session_id}")
async def notebook_chat_ws(websocket: WebSocket, editor_session_id: str) -> None:
    """Drive one notebook-chat session over a single WebSocket.

    Args:
        websocket: The incoming connection.  ``?notebook_id=…`` is
            an optional query parameter — when present, the
            Phase-105.6 agent-presence plugin tool fires from the
            in-process agent runs because the agent factory stamps
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
    settings: Settings = websocket.app.state.settings
    # Browsers surface a closed-before-accept handshake as a generic
    # "connection refused" — the WS close code + reason never arrive
    # on the client.  Accept first, then close with a meaningful code
    # so the AI-Assistant drawer can render an actionable error.
    await websocket.accept()
    if not settings.editor_chat.enabled:
        await websocket.close(code=4503, reason="editor_chat_disabled")
        return
    user = resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401, reason="not_authenticated")
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
    queue = subscribe(editor_session_id)
    cancel_event = threading.Event()
    active_turn: dict[str, Any] = {"id": None, "task": None}

    pump_task = asyncio.create_task(
        _pump_broker(websocket, queue),
        name=f"notebook-chat-pump-{editor_session_id[:8]}",
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
                notebook_id=notebook_id,
                cancel_event=cancel_event,
                active_turn=active_turn,
            )
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError, Exception:  # noqa: BLE001
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
    notebook_id: str | None,
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
            websocket,
            request_id=None,
            code="bad_frame",
            message="frame must be a JSON object",
        )
        return
    frame: dict[str, Any] = {str(k): v for k, v in frame_any.items()}  # type: ignore[reportUnknownVariableType]
    request_id_raw = frame.get("id")
    request_id: int | None = request_id_raw if isinstance(request_id_raw, int) else None
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
            notebook_id=notebook_id,
            cancel_event=cancel_event,
            active_turn=active_turn,
        )
    elif method == "cancel":
        cancel_event.set()
        await _send_reply(websocket, request_id=request_id, result={"cancelled": True})
    elif method == "reset":
        reset_session(factory, chat_session_id=chat_session_id)
        await _send_reply(websocket, request_id=request_id, result={"reset": True})
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
    notebook_id: str | None,
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
                    surface="notebook",
                    notebook_id=notebook_id,
                )
            except ValidationError as exc:
                publish(
                    editor_session_id,
                    ChatEvent(kind="error", payload={"detail": str(exc)}),
                )
                return
            except Exception as exc:  # noqa: BLE001 — bubble to client
                logger.exception("notebook chat turn failed")
                publish(
                    editor_session_id,
                    ChatEvent(kind="error", payload={"detail": str(exc)}),
                )
                return
            # Drain pending publish callbacks before enqueuing the
            # terminal frame.  Same rationale as ``sql_chat_ws``.
            await asyncio.sleep(0)
            if result.cancelled:
                publish(
                    editor_session_id,
                    ChatEvent(kind="cancelled", payload={"turn_id": turn_id}),
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
        name=f"notebook-chat-turn-{turn_id[:8]}",
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


async def _send_notify(websocket: WebSocket, *, kind: str, params: dict[str, Any]) -> None:
    """Send a ``{"notify": kind, "params": params}`` frame."""
    await websocket.send_text(json.dumps({"notify": kind, "params": params}))


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


__all__ = ["router"]
