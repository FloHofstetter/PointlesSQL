"""Lens read-only Q&A service layer.

Lens is the analyst-facing chat-style surface that exposes read-only
data Q&A over two transports: the browser chat UI at ``/lens`` and an
MCP (Model Context Protocol) server for IDE consumers.  Both
transports share the same tool registry and audit-trail substrate.

Layout:

* ``_sessions``      — :class:`LensSession` CRUD helpers
                        (workspace-scoped, owner-scoped).
* ``_messages``      — :class:`LensMessage` append + list helpers.
* ``_provider_creds`` — Fernet-encrypted BYO LLM key storage
                         (one credential per ``(workspace, provider)``).
* ``provenance``     — unified row/column/value lineage trace
                       .
* ``tools``          — Pydantic-typed tool registry shared between
                        the browser chat-loop and the MCP server
                       .
* ``cost_gate``      — auto-LIMIT + EXPLAIN-cost cap + per-session
                        budget.
* ``llm_provider``   — OpenAI / Anthropic SDK adapters for the
                        browser chat-loop.
* ``mcp_server``     — FastMCP-based stdio + SSE transport
                       .
* ``_chat_loop``     — orchestrates user-message → tool-dispatch →
                        assistant-message for the browser surface
                       .
"""

from __future__ import annotations

from pointlessql.services.lens._messages import (
    append_message,
    list_session_messages,
)
from pointlessql.services.lens._provider_creds import (
    decrypt_provider_key,
    delete_provider_creds,
    get_provider_creds,
    list_provider_creds,
    upsert_provider_creds,
)
from pointlessql.services.lens._sessions import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    touch_session,
    update_session_cost,
)

__all__ = [
    "append_message",
    "create_session",
    "decrypt_provider_key",
    "delete_provider_creds",
    "delete_session",
    "get_provider_creds",
    "get_session",
    "list_provider_creds",
    "list_session_messages",
    "list_sessions",
    "touch_session",
    "update_session_cost",
    "upsert_provider_creds",
]
