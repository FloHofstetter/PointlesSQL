"""MCP server bindings for the Lens tool registry (Phase 65.4).

Exposes :data:`pointlessql.services.lens.tools.ALL_TOOLS` over the
Model Context Protocol so IDE consumers (Claude Desktop, Cursor,
Hermes-as-MCP-client) can call the same tool surface as the browser
chat-loop.

Two transports share the underlying :class:`FastMCP` instance:

* **stdio** — :func:`run_lens_mcp_stdio` — for Claude Desktop config
  blocks.  Reads ``LENS_API_KEY`` from the env, resolves to an
  ``api_keys`` row, and runs forever on stdin/stdout.
* **SSE / HTTP** — :func:`build_lens_mcp_sse_app` — exposes a
  Starlette app that mounts under ``/mcp`` for Bearer-authenticated
  network access.

Auth: every transport resolves a Bearer token (env or header) to a
workspace-scoped :class:`SessionContext`; tools then run inside that
context and inherit workspace + audit-trail propagation.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from pointlessql.config import Settings, get_settings
from pointlessql.services.api_keys import KeyEntry, verify_bearer
from pointlessql.services.lens.tools import (
    ALL_TOOLS,
    SessionContext,
    ToolDef,
    execute_tool_with_audit,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

LENS_API_KEY_ENV = "LENS_API_KEY"  # pragma: allowlist secret
"""Environment variable carrying the analyst Bearer for stdio transport."""


class LensMcpAuthError(RuntimeError):
    """Raised when the MCP transport cannot resolve a usable Bearer key."""


def resolve_lens_key(
    factory: sessionmaker[Session],
    *,
    bearer_value: str | None,
) -> KeyEntry:
    """Resolve *bearer_value* to a :class:`KeyEntry` with the analyst scope.

    Mirrors the Bearer-auth path used by the FastAPI middleware but
    surfaces the failure as :class:`LensMcpAuthError` so the MCP
    transports can return a clean error rather than crash.

    Args:
        factory: SQLAlchemy session factory bound to the metadata DB.
        bearer_value: Raw secret (without the ``Bearer `` prefix) or
            full ``Bearer <secret>`` header.  ``None`` raises.

    Returns:
        The matching :class:`KeyEntry`.

    Raises:
        LensMcpAuthError: When the bearer is missing, malformed,
            unknown, revoked, or lacks both the ``analyst`` and
            ``auditor`` scopes (auditor is allowed because it is a
            superset of analyst, mirroring the route gate).
    """
    if not bearer_value:
        raise LensMcpAuthError(
            f"Lens MCP server requires a Bearer key.  Set "
            f"{LENS_API_KEY_ENV} (stdio) or send "
            f"'Authorization: Bearer <secret>' (SSE)."
        )
    header = (
        bearer_value
        if bearer_value.lower().startswith("bearer ")
        else f"Bearer {bearer_value}"
    )
    entry = verify_bearer(header, factory)
    if entry is None:
        raise LensMcpAuthError("Lens MCP Bearer key not recognised.")
    if not (entry.analyst or entry.auditor):
        raise LensMcpAuthError(
            f"Lens MCP key {entry.name!r} carries neither analyst "
            f"nor auditor scope; refusing connection."
        )
    return entry


def build_session_context_for_key(
    *,
    key: KeyEntry,
    factory: sessionmaker[Session],
    settings: Settings,
) -> SessionContext:
    """Construct a :class:`SessionContext` bound to *key*'s workspace.

    Args:
        key: The resolved :class:`KeyEntry` from :func:`resolve_lens_key`.
        factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.

    Returns:
        A :class:`SessionContext` with ``user_id=None`` (API-key
        callers are workspace-scoped, not user-scoped) and
        ``lens_session_id=None`` (the MCP-driven path does not
        persist a chat thread today; every tool call is stateless
        from the audit-trail point of view, but ``query_history``
        still records the SQL executions).
    """
    return SessionContext(
        workspace_id=key.workspace_id,
        user_id=None,
        lens_session_id=None,
        factory=factory,
        settings=settings,
        uc_client=None,
    )


def create_lens_mcp_server(
    *,
    factory: sessionmaker[Session],
    settings: Settings,
    api_key_secret: str | None = None,
) -> FastMCP:
    """Build a configured FastMCP instance with every Lens tool registered.

    Each :class:`ToolDef` in :data:`ALL_TOOLS` becomes one MCP tool;
    its executor is wrapped via :func:`execute_tool_with_audit` so
    the lens_messages audit trail is honored even on the MCP path.

    Args:
        factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.
        api_key_secret: Bearer secret pre-resolved at server-build
            time (stdio transport reads ``LENS_API_KEY`` once and
            caches the workspace context).  ``None`` is allowed for
            SSE transport, which resolves keys per request.

    Returns:
        Ready-to-run :class:`FastMCP`.

    Raises:
        LensMcpAuthError: When *api_key_secret* is set but does not
            resolve to a usable key.
    """  # noqa: DOC502 — LensMcpAuthError raised by resolve_lens_key
    mcp = FastMCP("PointlesSQL Lens")

    # Pre-resolve the Bearer for stdio transport.  SSE transport
    # passes ``api_key_secret=None`` and resolves per-request via the
    # Starlette dependency layer.
    cached_ctx: SessionContext | None = None
    if api_key_secret is not None:
        key = resolve_lens_key(factory, bearer_value=api_key_secret)
        cached_ctx = build_session_context_for_key(
            key=key, factory=factory, settings=settings
        )

    for tool in ALL_TOOLS:
        _register_tool_on_mcp(mcp, tool, cached_ctx, factory, settings)

    return mcp


def _register_tool_on_mcp(
    mcp: FastMCP,
    tool: ToolDef,
    cached_ctx: SessionContext | None,
    factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    """Register one Lens :class:`ToolDef` as an MCP tool.

    The wrapper closes over *tool*, *cached_ctx*, *factory*, and
    *settings*, then exposes a single ``async def`` taking the input
    model dict and returning the output model dict.  FastMCP infers
    the JSON schema from type hints; we pass the input model class
    directly so MCP's introspection works.
    """

    async def _wrapped(args: dict[str, Any]) -> dict[str, Any]:
        ctx = cached_ctx or _ephemeral_context(factory, settings)
        return await execute_tool_with_audit(
            tool_name=tool.name,
            ctx=ctx,
            raw_args=args,
        )

    _wrapped.__doc__ = tool.description
    _wrapped.__name__ = tool.name
    mcp.add_tool(_wrapped, name=tool.name, description=tool.description)


def _ephemeral_context(
    factory: sessionmaker[Session], settings: Settings
) -> SessionContext:
    """Build a default workspace=1 context.

    Fallback used when the SSE transport hasn't injected a per-request
    context yet — keeps unit tests viable but never touches user
    data because the tools refuse cross-workspace reads.
    """
    return SessionContext(
        workspace_id=1,
        user_id=None,
        lens_session_id=None,
        factory=factory,
        settings=settings,
        uc_client=None,
    )


def run_lens_mcp_stdio(
    *,
    factory: sessionmaker[Session] | None = None,
    settings: Settings | None = None,
    api_key_secret: str | None = None,
) -> None:
    """Block on a stdio MCP server bound to the analyst's workspace.

    Reads :data:`LENS_API_KEY` from the env when *api_key_secret* is
    not passed.  Falls back to the install's default DB factory + a
    fresh :class:`Settings` instance when *factory* / *settings* are
    omitted.

    Args:
        factory: SQLAlchemy session factory.  ``None`` builds one via
            :func:`pointlessql.db.init_db`.
        settings: Resolved :class:`Settings`.  ``None`` constructs a
            fresh instance from env.
        api_key_secret: Bearer secret.  ``None`` reads from
            ``LENS_API_KEY``.

    Raises:
        LensMcpAuthError: When no Bearer secret is available or it
            does not resolve.
    """  # noqa: DOC502 — LensMcpAuthError raised by helper
    import asyncio

    from pointlessql.db import get_session_factory, init_db

    resolved_settings = settings or get_settings()
    if factory is None:
        try:
            resolved_factory = get_session_factory()
        except RuntimeError:
            init_db(resolved_settings.db.url)
            resolved_factory = get_session_factory()
    else:
        resolved_factory = factory
    secret = api_key_secret or os.environ.get(LENS_API_KEY_ENV)
    server = create_lens_mcp_server(
        factory=resolved_factory,
        settings=resolved_settings,
        api_key_secret=secret,
    )
    asyncio.run(server.run_stdio_async())


def build_lens_mcp_sse_app(
    *,
    factory: sessionmaker[Session],
    settings: Settings,
) -> Any:
    """Return a Starlette ASGI app exposing the Lens MCP over SSE.

    The returned app is mountable under ``/mcp`` from
    :mod:`pointlessql.api.main`.  Each connection resolves the
    ``Authorization: Bearer`` header per-request, so a single FastMCP
    instance serves every analyst.

    Note: Sprint 65.4 ships the SSE app shape but route-layer auth
    enforcement lands as a small wrapper in
    :mod:`pointlessql.api.mcp` that delegates to
    :func:`require_analyst` before forwarding to the FastMCP app.

    Args:
        factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.

    Returns:
        A Starlette app instance suitable for ``app.mount("/mcp",
        sse_app)``.
    """
    server = create_lens_mcp_server(
        factory=factory,
        settings=settings,
        api_key_secret=None,
    )
    return server.sse_app()
