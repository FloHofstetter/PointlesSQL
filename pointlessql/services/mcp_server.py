# pyright: reportUnusedFunction=false
# (every function in this module is registered as an MCP tool via the
#  @server.tool() decorator, so pyright's unused-function check is a false
#  positive here — the registry, not local code, holds the references.)
"""MCP server — publish the catalog as governed Model Context Protocol tools.

External AI clients (assistant desktop apps, IDEs, agents) speak the Model
Context Protocol; ``mcp_registry`` governs which *external* MCP services a
workspace trusts, but until now PointlesSQL exposed none of its own. This
module is the other half: it publishes a read-only view of the Unity
Catalog metadata — catalogs, schemas, tables, and per-table column detail —
as MCP tools so any MCP client can browse the lakehouse without a bespoke
integration.

Every tool forwards to the async :class:`UnityCatalogClient` facade, so the
same principal scoping and over-the-wire governance the web UI relies on
apply unchanged — nothing here reaches past the facade or reads the
metadata DB directly. The transport (stdio, SSE, …) is the caller's choice;
:mod:`pointlessql.cli.mcp_server` runs it over stdio.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pointlessql.services.unitycatalog import UnityCatalogClient


def build_server(uc_client: UnityCatalogClient, *, name: str = "pointlessql") -> FastMCP:
    """Build a FastMCP server exposing read-only Unity Catalog tools.

    The returned server is transport-agnostic; call ``run()`` on it (or mount
    its ASGI app) to serve. Each registered tool is a thin async wrapper over
    one facade method, so catalog permissions are enforced by soyuz-catalog
    exactly as they are for the web UI.

    Args:
        uc_client: The Unity Catalog facade every tool dispatches into.
        name: Server name advertised to connecting MCP clients.

    Returns:
        A configured :class:`FastMCP` instance ready to serve.
    """
    server = FastMCP(name)

    @server.tool()
    async def list_catalogs() -> list[dict[str, Any]]:
        """List the Unity Catalog catalogs visible to the configured principal.

        Returns:
            One dict per catalog, each carrying at least a ``name`` key.
        """
        return await uc_client.list_catalogs()

    @server.tool()
    async def list_schemas(catalog: str) -> list[dict[str, Any]]:
        """List the schemas inside one catalog.

        Args:
            catalog: Parent catalog name.

        Returns:
            One dict per schema.
        """
        return await uc_client.list_schemas(catalog)

    @server.tool()
    async def list_tables(catalog: str, schema: str) -> list[dict[str, Any]]:
        """List the tables inside one schema.

        Args:
            catalog: Parent catalog name.
            schema: Parent schema name.

        Returns:
            One dict per table.
        """
        return await uc_client.list_tables(catalog, schema)

    @server.tool()
    async def describe_table(catalog: str, schema: str, table: str) -> dict[str, Any]:
        """Return one table's full metadata (columns, comment, properties).

        Args:
            catalog: Parent catalog name.
            schema: Parent schema name.
            table: Table name.

        Returns:
            The table's metadata dict.
        """
        return await uc_client.get_table(catalog, schema, table)

    return server
