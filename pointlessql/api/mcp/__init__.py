"""SSE/HTTP MCP transport for the Lens read-only Q&A surface.

Exposes ``/mcp`` (SSE event-stream + POST /mcp/messages) for IDE
consumers that prefer network transport over stdio (Cursor, web-based
Claude Desktop, third-party MCP clients).

Auth model: every connection presents ``Authorization: Bearer <secret>``;
the secret must resolve to an ``api_keys`` row carrying either the
``analyst`` or the ``auditor`` scope.  Cookie auth is not honored on
the MCP path — it would let a browser tab silently call tools without
the analyst's awareness.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from pointlessql.services.lens.mcp_server import (
    LensMcpAuthError,
    build_lens_mcp_sse_app,
    resolve_lens_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])


@router.get("/mcp/health")
def mcp_health() -> dict[str, Any]:
    """Liveness probe — confirms the MCP transport is mounted.

    Does not validate auth; safe to call from monitoring without a
    Bearer key.

    Returns:
        ``{"status": "ok", "tools": <count>}``.
    """
    from pointlessql.services.lens.tools import ALL_TOOLS

    return {"status": "ok", "tools": len(ALL_TOOLS)}


def mount_lens_mcp_sse(app: Any) -> None:
    """Mount the FastMCP SSE app under ``/mcp/sse`` on *app*.

    Called from :mod:`pointlessql.api.main` after
    :func:`register_routers` so the MCP transport sits next to the
    other API routers.  Skips mounting when the install disables Lens
    (``settings.lens.enabled=False``).

    Args:
        app: The FastAPI / Starlette app instance.
    """
    settings = app.state.settings
    if not getattr(settings.lens, "enabled", True):
        logger.info("Lens disabled in settings; skipping MCP SSE mount.")
        return
    factory = app.state.session_factory
    sse_app = build_lens_mcp_sse_app(factory=factory, settings=settings)
    # FastMCP's sse_app already exposes its own internal routes
    # (/sse + /messages); mount it under /mcp so consumers see the
    # canonical paths /mcp/sse + /mcp/messages.
    app.mount("/mcp", sse_app)


def authorize_mcp_request(request: Request) -> None:
    """Enforce the Bearer-key gate before forwarding to FastMCP.

    Propagates :class:`LensMcpAuthError` raised by
    :func:`resolve_lens_key` (mapped to 403 by the global error
    handler) when the request lacks a usable analyst key.  Mounted
    onto every SSE/HTTP MCP route via FastAPI dependency injection.

    Args:
        request: Incoming FastAPI request.
    """
    factory = request.app.state.session_factory
    bearer = request.headers.get("authorization")
    resolve_lens_key(factory, bearer_value=bearer)


@router.get("/mcp/info")
def mcp_info(request: Request) -> JSONResponse:
    """Return the resolved Bearer's workspace scope, for client debugging.

    Validates the Bearer key the same way the SSE transport does and
    echoes back the workspace_id + scope flags so consumers can
    confirm they are connecting to the right tenant before opening
    the SSE stream.

    Args:
        request: Incoming FastAPI request.

    Returns:
        JSON envelope ``{"workspace_id", "key_name", "scopes": [...]}``
        on success, ``{"error": "..."}`` on auth failure (HTTP 403).
    """
    factory = request.app.state.session_factory
    bearer = request.headers.get("authorization")
    try:
        key = resolve_lens_key(factory, bearer_value=bearer)
    except LensMcpAuthError as exc:
        return JSONResponse(status_code=403, content={"error": str(exc)})
    scopes = []
    if key.analyst:
        scopes.append("analyst")
    if key.auditor:
        scopes.append("auditor")
    if key.supervisor:
        scopes.append("supervisor")
    return JSONResponse(
        content={
            "workspace_id": key.workspace_id,
            "key_name": key.name,
            "scopes": scopes,
        }
    )


__all__ = ["authorize_mcp_request", "mount_lens_mcp_sse", "router"]
