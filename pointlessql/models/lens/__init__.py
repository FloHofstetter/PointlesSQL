"""ORM models for the Lens read-only Q&A surface.

Lens is the analyst-facing chat-style surface that exposes
read-only data Q&A over two transports: a browser chat UI at ``/lens``
and an MCP (Model Context Protocol) server for IDE consumers.  Both
transports share the same tool registry; this package holds the
persistence layer.

Layout:

* ``_session``       — :class:`LensSession` (one chat thread per user
                        + workspace).
* ``_message``       — :class:`LensMessage` (one user / assistant /
                        tool turn within a session, plus tool-call
                        audit trail).
* ``_pinned_answer`` — :class:`LensPinnedAnswer` (admin-pinned
                        bookmarked answer rendered standalone analog
                        :class:`Dashboard`).
* ``_provider_creds` — :class:`LensProviderCreds` (per-workspace
                        Fernet-encrypted BYO LLM key for OpenAI /
                        Anthropic).
"""

from __future__ import annotations

from pointlessql.models.lens._message import LensMessage
from pointlessql.models.lens._pinned_answer import LensPinnedAnswer
from pointlessql.models.lens._provider_creds import (
    LENS_PROVIDERS,
    LensProviderCreds,
)
from pointlessql.models.lens._session import LensSession

__all__ = [
    "LENS_PROVIDERS",
    "LensMessage",
    "LensPinnedAnswer",
    "LensProviderCreds",
    "LensSession",
]
