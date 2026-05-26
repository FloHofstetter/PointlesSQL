"""Build a ``hermes_agent.AIAgent`` instance for a chat turn.

The plan calls hermes-agent in-process: each turn instantiates an
``AIAgent`` with the conversation history, hands it a synchronous
``stream_delta_callback`` that bridges back to the WS-send queue,
and lets the plugin (``hermes-plugin-pointlessql``) load via the
normal discovery path so all ``pql_*`` tools are available.

This module is the only place inside PointlesSQL that imports
``hermes_agent``.  Tests monkeypatch :func:`build_agent` with a
fake so the import is never triggered at test time.

adds a ``surface`` argument so the same factory serves
both the SQL-editor chat (``surface="sql"``, sets
``POINTLESSQL_CHAT_SESSION_ID``) and the notebook-editor AI
assistant (``surface="notebook"``, sets
``POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID``).  The plugin tools
self-gate on whichever env var is set, so the two surfaces never
register each other's propose tools.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Literal

from pointlessql.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from pointlessql.config import Settings

logger = logging.getLogger(__name__)

LLM_NOT_CONFIGURED_REASON: str = "LLM_NOT_CONFIGURED"
"""WebSocket close reason when the host has no LLM provider creds."""

ChatSurface = Literal["sql", "notebook"]
"""Discriminator for which env-var split the propose tools should see.

The plugin's ``pql_propose_sql`` tool gates on
``POINTLESSQL_CHAT_SESSION_ID``; the Phase-96 ``pql_propose_cell`` /
``pql_fix_cell`` / ``pql_explain_cell`` tools gate on
``POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID``.  Setting both at once
would register every tool in both surfaces, which is wrong — the
notebook chat must not have ``pql_propose_sql`` (no SQL editor to
post into) and the SQL chat must not have the cell-level tools (no
notebook to mutate).
"""

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
    surface: ChatSurface = "sql",
    notebook_id: str | None = None,
) -> Any:
    """Instantiate a fresh ``AIAgent`` for one turn.

    Args:
        settings: PointlesSQL settings (carries
            :class:`EditorChatSettings` with model/provider defaults).
        agent_run_id: The chat session's ``agent_run_id``.  Set
            into ``POINTLESSQL_AGENT_RUN_ID`` env before the call
            so the plugin's HTTP client tags every tool-call.
        editor_session_id: UUID7 of the chat session.  Set into
            ``POINTLESSQL_CHAT_SESSION_ID`` (SQL surface) or
            ``POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID`` (notebook
            surface) so the matching plugin propose tools register
            and know where to push drafts.
        on_token: Synchronous callback the agent calls with each
            streamed text delta.  The turn runner uses this to
            forward tokens to the WS send queue.
        surface: Which propose-tool family the plugin should
            register inside this run.  Defaults to ``"sql"`` for
            backwards-compat with SQL callers; the notebook chat
            WS passes ``"notebook"``.
        notebook_id: When set, stamped into
            ``POINTLESSQL_NOTEBOOK_ID`` so the plugin's
            ``propose_cell`` / ``fix_cell`` / ``explain_cell`` tools
            can fire pre/post ``coedit/agent-presence`` broadcasts
            that light up a robot pseudo-peer on every connected
            editor tab.  ``None`` clears the env so a previous
            notebook's id doesn't leak into a fresh chat session.

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
    # Clear the other surface's env var first so a process that
    # served a SQL chat last turn doesn't accidentally re-register
    # pql_propose_sql for a notebook turn (and vice versa).  The
    # plugin reads env at register-time, not per-call.
    if surface == "sql":
        os.environ["POINTLESSQL_CHAT_SESSION_ID"] = editor_session_id
        os.environ.pop("POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID", None)
        os.environ.pop("POINTLESSQL_NOTEBOOK_ID", None)
    else:
        os.environ["POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID"] = editor_session_id
        os.environ.pop("POINTLESSQL_CHAT_SESSION_ID", None)
        if notebook_id:
            os.environ["POINTLESSQL_NOTEBOOK_ID"] = notebook_id
        else:
            os.environ.pop("POINTLESSQL_NOTEBOOK_ID", None)

    # Import lazily so tests that monkeypatch ``build_agent`` never
    # pull hermes_agent into the process.  hermes_agent has no
    # published type stubs; pyright pragmas cover the import + the
    # unknown class symbol.
    from run_agent import (  # pyright: ignore[reportMissingTypeStubs, reportMissingImports]
        AIAgent,
    )

    kwargs: dict[str, Any] = {
        "model": settings.editor_chat.default_model,
        "stream_delta_callback": on_token,
    }
    if settings.editor_chat.provider:
        kwargs["provider"] = settings.editor_chat.provider
    if settings.editor_chat.base_url:
        kwargs["base_url"] = settings.editor_chat.base_url
    agent: Any = AIAgent(**kwargs)  # pyright: ignore[reportUnknownVariableType]
    return agent
