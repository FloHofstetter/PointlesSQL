"""Shared engine behind the editor-chat WebSocket surfaces.

The SQL-editor chat (``/ws/sql/chat/{editor_session_id}``) and the
notebook AI assistant (``/ws/notebook/chat/{editor_session_id}``)
speak the same JSON-RPC envelope:

* Inbound frames: ``{"id": int, "method": str, "params": dict}``.
* Outbound replies: ``{"id": int, "result": dict}`` or ``{"id": int,
  "error": {"code": str, "message": str}}``.
* Outbound notifications: ``{"notify": str, "params": dict}``.

Methods handled here:

* ``prompt`` — start a new turn with ``params.text``.
* ``cancel`` — set the cancel-event on the active turn.
* ``reset`` — clear the conversation history.

Surface-specific methods (the SQL editor's ``refine``) plug in via
``extra_frame_handler``; the accept / feature-gate / auth prelude,
the broker pump, turn execution, and teardown are shared.

Two deliberate indirections keep the route modules' test seams
intact:

* The LLM-configured gate arrives as the ``llm_gate`` argument
  instead of being imported here — each route module keeps
  ``check_llm_configured`` as a module-level global and forwards it
  per connection, so monkeypatches on
  ``pointlessql.api.sql_chat_ws.check_llm_configured`` (and the
  notebook twin) stay effective.
* :func:`get_turn_executor` keeps one thread pool *per surface
  prefix* — the SQL and notebook surfaces retain their separate
  pools rather than sharing one.

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
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from pointlessql.api._ws_error import send_error as _send_error
from pointlessql.api._ws_scaffold import authenticate_or_close
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
from pointlessql.services.editor_chat._agent_factory import LLM_NOT_CONFIGURED_REASON

if TYPE_CHECKING:
    from pointlessql.config import Settings

logger = logging.getLogger(__name__)

PromptRunner = Callable[[int | None, dict[str, Any]], Awaitable[None]]
"""Run the prompt pipeline for a synthesized ``(request_id, params)``."""

ExtraFrameHandler = Callable[
    [WebSocket, int | None, str | None, dict[str, Any], PromptRunner],
    Awaitable[bool],
]
"""Surface-specific method hook.

Called with ``(websocket, request_id, method, params, run_prompt)``
for any method the engine does not handle itself; returns ``True``
when the frame was consumed, ``False`` to fall through to the
engine's ``unknown_method`` error envelope.
"""

_executors: dict[str, ThreadPoolExecutor] = {}
_executors_lock: threading.Lock = threading.Lock()


def get_turn_executor(prefix: str, max_workers: int) -> ThreadPoolExecutor:
    """Return the per-prefix singleton thread pool for AIAgent runs.

    Each chat surface keeps its own pool (keyed and thread-named by
    *prefix*) so a burst of turns on one surface cannot starve the
    other; ``max_workers`` only applies when the pool is first
    created.

    Args:
        prefix: Thread-name prefix and registry key, e.g.
            ``"sql-chat-turn"``.
        max_workers: Pool size; clamped to at least 1.

    Returns:
        The lazily-created :class:`ThreadPoolExecutor` for *prefix*.
    """
    with _executors_lock:
        executor = _executors.get(prefix)
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=max(1, max_workers),
                thread_name_prefix=prefix,
            )
            _executors[prefix] = executor
    return executor


async def run_chat_session(
    websocket: WebSocket,
    editor_session_id: str,
    *,
    surface: str,
    llm_gate: Callable[[], bool],
    notebook_id: str | None = None,
    extra_frame_handler: ExtraFrameHandler | None = None,
) -> None:
    """Drive one editor-chat session over a single WebSocket.

    Args:
        websocket: The incoming connection; accepted here.
        editor_session_id: Stable id minted at page render — keys
            the chat-session row and the broker channel.
        surface: ``"sql"`` or ``"notebook"``; forwarded to the turn
            pipeline and used to name the pump/turn tasks and the
            per-surface executor pool.
        llm_gate: Zero-arg callable reporting whether an LLM
            provider is configured.  Passed in by the route module
            (resolved from its globals per connection) so the
            module attribute remains the monkeypatch target.
        notebook_id: Optional notebook UUID forwarded to the turn
            pipeline; only meaningful for ``surface="notebook"``.
        extra_frame_handler: Optional hook for surface-specific
            methods, consulted before the unknown-method error.
    """
    settings: Settings = websocket.app.state.settings
    # Browsers surface a closed-before-accept handshake as a generic
    # "connection refused" — the WS close code + reason never arrive
    # on the client.  Accept first, then close with a meaningful code
    # so the chat drawer can render an actionable error.
    await websocket.accept()
    if not settings.editor_chat.enabled:
        await websocket.close(code=4503, reason="editor_chat_disabled")
        return
    user = await authenticate_or_close(websocket)
    if user is None:
        return
    if not llm_gate():
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
        name=f"{surface}-chat-pump-{editor_session_id[:8]}",
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
                surface=surface,
                notebook_id=notebook_id,
                cancel_event=cancel_event,
                active_turn=active_turn,
                extra_frame_handler=extra_frame_handler,
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
    surface: str,
    notebook_id: str | None,
    cancel_event: threading.Event,
    active_turn: dict[str, Any],
    extra_frame_handler: ExtraFrameHandler | None,
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
    request_id: int | None = request_id_raw if isinstance(request_id_raw, int) else None
    method_raw = frame.get("method")
    method: str | None = method_raw if isinstance(method_raw, str) else None
    params_raw = frame.get("params")
    params: dict[str, Any] = (
        {str(k): v for k, v in params_raw.items()}  # type: ignore[reportUnknownVariableType]
        if isinstance(params_raw, dict)
        else {}
    )

    async def _run_prompt(prompt_request_id: int | None, prompt_params: dict[str, Any]) -> None:
        await _handle_prompt(
            websocket,
            request_id=prompt_request_id,
            params=prompt_params,
            settings=settings,
            factory=factory,
            editor_session_id=editor_session_id,
            chat_session_id=chat_session_id,
            agent_run_id=agent_run_id,
            surface=surface,
            notebook_id=notebook_id,
            cancel_event=cancel_event,
            active_turn=active_turn,
        )

    if method == "prompt":
        await _run_prompt(request_id, params)
    elif method == "cancel":
        cancel_event.set()
        await _send_reply(websocket, request_id=request_id, result={"cancelled": True})
    elif method == "reset":
        reset_session(factory, chat_session_id=chat_session_id)
        await _send_reply(websocket, request_id=request_id, result={"reset": True})
    else:
        if extra_frame_handler is not None and await extra_frame_handler(
            websocket, request_id, method, params, _run_prompt
        ):
            return
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
    surface: str,
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
            executor = get_turn_executor(
                f"{surface}-chat-turn",
                settings.editor_chat.executor_workers,
            )
            try:
                result = await run_turn(
                    settings=settings,
                    executor=executor,
                    editor_session_id=editor_session_id,
                    agent_run_id=agent_run_id,
                    user_message=text,
                    conversation_history=history,
                    cancel_event=cancel_event,
                    surface=surface,
                    notebook_id=notebook_id,
                )
            except ValidationError as exc:
                publish(
                    editor_session_id,
                    ChatEvent(kind="error", payload={"detail": str(exc)}),
                )
                return
            except Exception:  # noqa: BLE001 — bubble a safe message to client
                # Never forward str(exc): an unexpected failure can carry
                # internal detail (paths, secrets). Log the full trace
                # server-side and send the client a fixed, safe message.
                logger.exception("%s chat turn failed", surface)
                publish(
                    editor_session_id,
                    ChatEvent(
                        kind="error",
                        payload={
                            "detail": "The chat turn failed unexpectedly.",
                            "code": "chat_turn_failed",
                        },
                    ),
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
        name=f"{surface}-chat-turn-{turn_id[:8]}",
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


__all__ = [
    "ExtraFrameHandler",
    "PromptRunner",
    "get_turn_executor",
    "run_chat_session",
]
