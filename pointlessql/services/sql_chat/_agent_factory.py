"""Build a ``hermes_agent.AIAgent`` instance for a chat turn.

The plan calls hermes-agent in-process: each turn instantiates an
``AIAgent`` with the conversation history, hands it a synchronous
``stream_delta_callback`` that bridges back to the WS-send queue,
and lets the plugin (``hermes-plugin-pointlessql``) load via the
normal discovery path so all ``pql_*`` tools are available.

This module is the only place inside PointlesSQL that imports
``hermes_agent``.  Tests monkeypatch :func:`build_agent` with a
fake so the import is never triggered at test time.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from pointlessql.config import Settings

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_REASON: str = "LLM_NOT_CONFIGURED"
"""WebSocket close reason when the host has no LLM provider creds."""


_PROVIDER_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "OLLAMA_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "MISTRAL_API_KEY",
    "XAI_API_KEY",
)


def check_llm_configured() -> bool:
    """Return ``True`` when at least one supported provider env var is set."""
    return any(os.environ.get(key, "").strip() for key in _PROVIDER_ENV_KEYS)


def build_agent(
    *,
    settings: Settings,
    agent_run_id: str,
    editor_session_id: str,
    on_token: Callable[[str | None], None],
) -> Any:
    """Instantiate a fresh ``AIAgent`` for one turn.

    Args:
        settings: PointlesSQL settings (carries
            :class:`SqlChatSettings` with model/provider defaults).
        agent_run_id: The chat session's ``agent_run_id``.  Set
            into ``POINTLESSQL_AGENT_RUN_ID`` env before the call
            so the plugin's HTTP client tags every tool-call.
        editor_session_id: UUID7 of the chat session.  Set into
            ``POINTLESSQL_CHAT_SESSION_ID`` env so the
            ``pql_propose_sql`` tool registers and knows where to
            push DML/DDL drafts.
        on_token: Synchronous callback the agent calls with each
            streamed text delta.  The turn runner uses this to
            forward tokens to the WS send queue.

    Returns:
        An object with ``run_conversation(user_message, *,
        conversation_history) -> dict`` compatible with
        ``hermes_agent.AIAgent``.

    Raises:
        ValidationError: When no LLM provider env var is set;
            propagated to the WS-open path so we can close 1011
            with a humanised reason before the first token.
    """
    if not check_llm_configured():
        raise ValidationError(
            "No LLM provider configured — set ANTHROPIC_API_KEY (or "
            "OPENAI_API_KEY, etc.) before opening the chat drawer."
        )

    os.environ["POINTLESSQL_AGENT_RUN_ID"] = agent_run_id
    os.environ["POINTLESSQL_CHAT_SESSION_ID"] = editor_session_id

    # Import lazily so tests that monkeypatch ``build_agent`` never
    # pull hermes_agent into the process.  hermes_agent has no
    # published type stubs; pyright pragmas cover the import + the
    # unknown class symbol.
    from run_agent import (  # pyright: ignore[reportMissingTypeStubs, reportMissingImports]
        AIAgent,
    )

    kwargs: dict[str, Any] = {
        "model": settings.sql_chat.default_model,
        "stream_delta_callback": on_token,
    }
    if settings.sql_chat.provider:
        kwargs["provider"] = settings.sql_chat.provider
    if settings.sql_chat.base_url:
        kwargs["base_url"] = settings.sql_chat.base_url
    agent: Any = AIAgent(**kwargs)  # pyright: ignore[reportUnknownVariableType]
    return agent
