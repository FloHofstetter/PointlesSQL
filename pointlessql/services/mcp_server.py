# pyright: reportUnusedFunction=false
# (every function in this module is registered as an MCP tool via the
#  @server.tool() decorator, so pyright's unused-function check is a false
#  positive here — the registry, not local code, holds the references.)
"""MCP server — publish the catalog as governed Model Context Protocol tools.

External AI clients (assistant desktop apps, IDEs, agents) speak the Model
Context Protocol; ``mcp_registry`` governs which *external* MCP services a
workspace trusts, but until now PointlesSQL exposed none of its own. This
module is the other half: it publishes a read-only view of the Unity
Catalog metadata — catalogs, schemas, tables, column detail, lineage,
effective permissions, and metric views (the semantic layer) — as MCP
tools so any MCP client can browse the lakehouse without a bespoke
integration.

Every tool forwards to the async :class:`UnityCatalogClient` facade, so the
same principal scoping and over-the-wire governance the web UI relies on
apply unchanged — nothing here reaches past the facade or reads the
metadata DB directly. The transport (stdio, SSE, …) is the caller's choice;
:mod:`pointlessql.cli.mcp_server` runs it over stdio.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from pointlessql.services.unitycatalog import UnityCatalogClient

#: A governed SELECT runner: ``(sql, limit) -> {columns, rows, …}``. Injected so
#: the server stays decoupled from the Lens session-context plumbing.
QueryRunner = Callable[[str, int | None], Awaitable[dict[str, Any]]]


def build_server(
    uc_client: UnityCatalogClient,
    *,
    name: str = "pointlessql",
    query_runner: QueryRunner | None = None,
) -> FastMCP:
    """Build a FastMCP server exposing read-only Unity Catalog tools.

    The returned server is transport-agnostic; call ``run()`` on it (or mount
    its ASGI app) to serve. Each registered tool is a thin async wrapper over
    one facade method, so catalog permissions are enforced by soyuz-catalog
    exactly as they are for the web UI.

    Args:
        uc_client: The Unity Catalog facade every tool dispatches into.
        name: Server name advertised to connecting MCP clients.
        query_runner: Optional governed SELECT runner. When supplied, a
            ``run_select`` tool is registered that forwards to it; when
            ``None`` the server is metadata-only (no data access).

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

    @server.tool()
    async def get_lineage(full_name: str, depth: int = 3) -> dict[str, Any]:
        """Return the upstream/downstream lineage graph for a table.

        Args:
            full_name: Three-part ``catalog.schema.table`` name.
            depth: How many hops of lineage to traverse (default 3).

        Returns:
            The lineage graph (nodes + edges) as a dict.
        """
        return await uc_client.get_lineage(full_name, depth)

    @server.tool()
    async def get_effective_permissions(
        securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        """Return the effective permissions on a securable for the principal.

        Args:
            securable_type: UC securable kind (e.g. ``"table"``, ``"schema"``).
            full_name: The securable's fully-qualified name.

        Returns:
            One dict per effective privilege grant.
        """
        return await uc_client.get_effective_permissions(securable_type, full_name)

    @server.tool()
    async def list_metric_views(catalog: str, schema: str) -> list[dict[str, Any]]:
        """List the metric views (semantic-layer measures) inside one schema.

        Args:
            catalog: Parent catalog name.
            schema: Parent schema name.

        Returns:
            One dict per metric view.
        """
        return await uc_client.list_metric_views(catalog, schema)

    @server.tool()
    async def get_metric_view(full_name: str) -> dict[str, Any]:
        """Return one metric view's definition (dimensions + measures).

        Args:
            full_name: Three-part ``catalog.schema.metric_view`` name.

        Returns:
            The metric view's definition dict.
        """
        return await uc_client.get_metric_view(full_name)

    if query_runner is not None:

        @server.tool()
        async def run_select(sql: str, limit: int | None = None) -> dict[str, Any]:
            """Run a read-only SELECT against the catalog and return its rows.

            The statement is validated as a single SELECT (DDL/DML rejected),
            auto-LIMITed, and gated by an EXPLAIN cost cap before it executes.

            Args:
                sql: A single SELECT statement.
                limit: Optional row cap (the gate injects a default otherwise).

            Returns:
                A dict with ``columns``, ``rows``, the gated ``executed_sql``,
                and a cost estimate.
            """
            return await query_runner(sql, limit)

    return server
