"""HTTP/SSE transport for the read-only catalog MCP server.

The catalog MCP server (:func:`pointlessql.services.mcp_server.build_server`)
publishes Unity Catalog metadata — catalogs → schemas → tables, lineage,
effective permissions, metric views, keyword search — as Model Context
Protocol tools. Over stdio it is reachable through the ``pointlessql-mcp``
console script; this module exposes the same server over the network by
mounting its SSE ASGI app on the main FastAPI app, so hosted AI clients
(assistant apps, IDEs) can connect over HTTP without spawning the binary.

Auth + scoping: every connection is authenticated as the request's
principal (the same cookie / API-key identity the rest of the app resolves
via :func:`effective_principal`). Anonymous callers are refused with 401.
The authenticated principal's :class:`UnityCatalogClient` is bound to the
in-flight request through :data:`_active_uc`, so the single shared FastMCP
server runs each caller's tools under their own catalog grants — soyuz
enforces them over the wire exactly as it does for the web UI.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from pointlessql.api.dependencies import effective_principal, uc_client_for_principal
from pointlessql.services.mcp_server import build_server
from pointlessql.services.unitycatalog import UnityCatalogClient

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

#: Path the catalog MCP SSE transport is mounted under. Kept distinct from the
#: Lens ``/mcp`` surface so the two MCP servers never shadow each other.
CATALOG_MCP_MOUNT = "/catalog-mcp"

#: The per-principal UC facade bound to the in-flight catalog MCP request. The
#: shared FastMCP server is built once over a proxy (:class:`_PrincipalScopedUC`)
#: that reads this var, so one server instance serves every caller while each
#: tool call still runs under the connecting principal's grants.
_active_uc: ContextVar[UnityCatalogClient | None] = ContextVar(
    "catalog_mcp_active_uc", default=None
)


class _PrincipalScopedUC:
    """A UC-facade stand-in dispatching to the request's principal-scoped client.

    :func:`pointlessql.services.mcp_server.build_server` closes over a single
    facade instance, but the network transport needs each connection to run
    under its own principal. This proxy forwards every attribute access (the
    async tool methods the tools call) to the :class:`UnityCatalogClient` bound
    to the current request via :data:`_active_uc`, so the shared server enforces
    per-caller grants without rebuilding the tool registry per request.
    """

    def __getattr__(self, name: str) -> Any:
        """Resolve *name* on the request's active per-principal UC client.

        Args:
            name: The facade attribute (an async tool method) being accessed.

        Returns:
            The attribute looked up on the active per-principal client.

        Raises:
            RuntimeError: When no principal client is bound — i.e. a tool ran
                outside the auth wrapper that sets :data:`_active_uc`.
        """
        client = _active_uc.get()
        if client is None:
            raise RuntimeError("catalog MCP tool invoked outside a principal-scoped request")
        return getattr(client, name)


def build_catalog_mcp_sse_app() -> ASGIApp:
    """Return the catalog MCP server's SSE ASGI app over the scoped facade.

    The server is built once with the :class:`_PrincipalScopedUC` proxy, so a
    single FastMCP instance (and its SSE transport) serves every connection
    while each tool call dispatches to the connecting principal's client.

    Returns:
        The FastMCP SSE Starlette app, ready to wrap + mount.
    """
    server = build_server(
        cast("UnityCatalogClient", _PrincipalScopedUC()),
        name="pointlessql-catalog",
    )
    # FastMCP defaults to localhost-only DNS-rebinding protection (allowed
    # hosts 127.0.0.1 / localhost), which suits a stdio-replacement bound to
    # the loopback but rejects every client reaching a deployed PointlesSQL at
    # its real hostname. Access is instead controlled by the principal gate in
    # _principal_scoped_asgi (401 for anonymous): API-key/bearer clients — the
    # intended consumers — carry no ambient credentials, and same-origin policy
    # stops a cross-origin browser from reading the SSE stream, so the
    # loopback host pin only gets in the way here.
    server.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    return server.sse_app()


def _principal_scoped_asgi(inner: ASGIApp, app: FastAPI) -> ASGIApp:
    """Wrap *inner* so each HTTP request runs under its caller's UC client.

    Resolves the effective principal the same way the rest of the app does,
    refuses anonymous callers with 401, binds the per-principal client to
    :data:`_active_uc` for the duration of the request, and forwards to the
    FastMCP ASGI app. For the long-lived SSE GET the binding stays in place
    for the whole connection, so the inline MCP run loop (and the tool tasks
    it spawns) inherit the connecting principal. Non-HTTP scopes (lifespan)
    pass straight through.

    Args:
        inner: The FastMCP SSE ASGI app to guard.
        app: The parent FastAPI app, for its ``state`` (settings + the shared
            per-principal client cache).

    Returns:
        An ASGI app enforcing principal auth + scoping around *inner*.
    """

    async def scoped(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        principal = effective_principal(request)
        if not principal:
            response = JSONResponse(
                {"error": "the catalog MCP endpoint requires an authenticated principal"},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        client = uc_client_for_principal(app.state, principal)
        token = _active_uc.set(client)
        try:
            await inner(scope, receive, send)
        finally:
            _active_uc.reset(token)

    return scoped


def mount_catalog_mcp(app: FastAPI) -> None:
    """Mount the catalog MCP SSE transport under ``/catalog-mcp`` on *app*.

    Builds the scoped server once and mounts its SSE app behind the
    principal-auth wrapper. Skips mounting when the install disables the
    network surface (``settings.catalog_mcp.enabled=False``); the stdio
    transport (``pointlessql-mcp``) is unaffected either way.

    Args:
        app: The FastAPI app to mount the transport on.
    """
    from pointlessql.config import get_settings

    if not get_settings().catalog_mcp.enabled:
        logger.info("catalog MCP network transport disabled in settings; not mounting.")
        return
    sse_app = build_catalog_mcp_sse_app()
    app.mount(CATALOG_MCP_MOUNT, _principal_scoped_asgi(sse_app, app))


__all__ = ["CATALOG_MCP_MOUNT", "build_catalog_mcp_sse_app", "mount_catalog_mcp"]
