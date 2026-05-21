"""Run one chat turn against ``hermes_agent.AIAgent``.

``AIAgent.run_conversation`` is synchronous and blocks until the
LLM + tool loop finishes.  We run it in a dedicated thread pool so
the FastAPI event loop stays responsive; the agent's
``stream_delta_callback`` is bridged into an asyncio queue via
``loop.call_soon_threadsafe`` so the WS coroutine can forward
tokens as ``notify`` frames as they arrive.

A turn is bounded: the cancel-event flips when the WS receives
``{"method": "cancel"}`` and the callback raises
:class:`StreamCancelled` on the next token, which bubbles out of
``run_conversation`` and ends the turn cleanly.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from pointlessql.services.editor_chat._agent_factory import ChatSurface
from pointlessql.services.editor_chat._broker import ChatEvent, publish

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pointlessql.config import Settings

logger = logging.getLogger(__name__)


class StreamCancelled(Exception):
    """Raised inside the streaming callback when the WS asked to cancel."""


@dataclass(frozen=True, slots=True)
class TurnResult:
    """Output of one chat turn.

    Attributes:
        final_response: Concatenated assistant text the LLM emitted.
            Empty string when the LLM only produced tool-calls and
            no closing prose.
        messages: Full transcript delta produced by this turn —
            user message + every tool message + assistant message.
            Appended to the chat-session's ``conversation_json``
            so the next turn carries the context.
        api_calls: Number of upstream LLM API calls the turn made.
            Surfaced in the ``final`` notify so the UI can show
            "Asked the model 3 times".
        cancelled: ``True`` when the turn ended because the WS
            asked to cancel rather than the LLM finishing naturally.
    """

    final_response: str
    messages: list[dict[str, Any]]
    api_calls: int
    cancelled: bool


async def run_turn(
    *,
    settings: Settings,
    executor: ThreadPoolExecutor,
    editor_session_id: str,
    agent_run_id: str,
    user_message: str,
    conversation_history: Sequence[dict[str, Any]],
    cancel_event: threading.Event,
    agent_builder: Any | None = None,
    surface: str = "sql",
    notebook_id: str | None = None,
) -> TurnResult:
    """Execute one chat turn end-to-end with streaming + cancel.

    Args:
        settings: PointlesSQL settings (carries chat config).
        executor: ThreadPoolExecutor where the blocking
            ``AIAgent.run_conversation`` runs.
        editor_session_id: Target chat session id used by the
            broker fan-out + the propose tool's env var.
        agent_run_id: The chat session's ``agent_run_id`` so
            tool-calls land on the correct run.
        user_message: New human prompt to send.
        conversation_history: Prior turns' messages.  Verbatim
            list shape ``AIAgent.run_conversation`` expects.
        cancel_event: ``threading.Event`` checked on every token;
            set from the WS side to abort mid-turn.
        agent_builder: Optional override of
            :func:`pointlessql.services.editor_chat._agent_factory.build_agent`
            — tests inject a :class:`FakeAIAgent` factory here.
        surface: Which propose-tool family the plugin should
            register inside this turn.  ``"sql"`` (default) for
            the Phase-91 SQL chat; ``"notebook"`` for the Phase-96
            notebook AI assistant.  Forwarded to ``build_agent``.
        notebook_id: Phase 105.6 — optional notebook UUID
            forwarded to ``build_agent`` so the plugin can fire
            ``coedit/agent-presence`` broadcasts.  Only meaningful
            for ``surface="notebook"``; ignored otherwise.

    Returns:
        A :class:`TurnResult` carrying the assistant reply, the
        appended messages, the LLM-call count, and the cancel flag.
    """
    loop = asyncio.get_running_loop()
    builder = agent_builder

    def on_token(text: str | None) -> None:
        """Forward each token to the broker; raise if cancelled."""
        if cancel_event.is_set():
            raise StreamCancelled
        # ``None`` is hermes-agent's tool-call sentinel — we forward
        # it as a discrete frame so the UI can show "thinking..." /
        # "calling tool".
        if text is None:
            loop.call_soon_threadsafe(
                publish,
                editor_session_id,
                ChatEvent(kind="tool_phase", payload={}),
            )
            return
        loop.call_soon_threadsafe(
            publish,
            editor_session_id,
            ChatEvent(kind="token", payload={"text": text}),
        )

    def _run_sync() -> TurnResult:
        nonlocal builder
        if builder is None:
            from pointlessql.services.editor_chat._agent_factory import build_agent

            builder = build_agent
        agent = builder(
            settings=settings,
            agent_run_id=agent_run_id,
            editor_session_id=editor_session_id,
            on_token=on_token,
            surface=cast(ChatSurface, surface),
            notebook_id=notebook_id,
        )
        try:
            result = agent.run_conversation(
                user_message,
                conversation_history=list(conversation_history),
            )
        except StreamCancelled:
            return TurnResult(
                final_response="",
                messages=[],
                api_calls=0,
                cancelled=True,
            )
        return TurnResult(
            final_response=str(result.get("final_response", "")),
            messages=_coerce_messages(result.get("messages")),
            api_calls=int(result.get("api_calls", 0) or 0),
            cancelled=False,
        )

    return await loop.run_in_executor(executor, _run_sync)


def _coerce_messages(raw: Any) -> list[dict[str, Any]]:
    """Tolerate hermes-agent returning ``None`` or a non-list."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:  # type: ignore[reportUnknownVariableType]
        if isinstance(item, dict):
            out.append({str(k): v for k, v in item.items()})  # type: ignore[reportUnknownVariableType]
    return out
