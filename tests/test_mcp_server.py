"""Tests for the catalog MCP server (governed read-only tool surface)."""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.services.mcp_server import build_server


class _FakeUC:
    """Minimal stand-in for ``UnityCatalogClient`` capturing tool dispatch."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def list_catalogs(self) -> list[dict[str, Any]]:
        self.calls.append(("list_catalogs", ()))
        return [{"name": "main"}]

    async def list_schemas(self, catalog_name: str) -> list[dict[str, Any]]:
        self.calls.append(("list_schemas", (catalog_name,)))
        return [{"name": "gold", "catalog_name": catalog_name}]

    async def list_tables(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        self.calls.append(("list_tables", (catalog_name, schema_name)))
        return [{"name": "orders"}]

    async def get_table(
        self, catalog_name: str, schema_name: str, table_name: str
    ) -> dict[str, Any]:
        self.calls.append(("get_table", (catalog_name, schema_name, table_name)))
        return {"name": table_name, "columns": [{"name": "id"}]}

    async def get_lineage(self, full_name: str, depth: int = 3) -> dict[str, Any]:
        self.calls.append(("get_lineage", (full_name, depth)))
        return {"nodes": [full_name], "edges": []}

    async def get_effective_permissions(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        self.calls.append(("get_effective_permissions", (securable_type, full_name)))
        return [{"privilege": "SELECT"}]

    async def list_metric_views(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        self.calls.append(("list_metric_views", (catalog_name, schema_name)))
        return [{"name": "revenue"}]

    async def get_metric_view(self, full_name: str) -> dict[str, Any]:
        self.calls.append(("get_metric_view", (full_name,)))
        return {"name": full_name, "measures": []}


def test_server_is_named_for_the_application() -> None:
    """The MCP server advertises the configured name to connecting clients."""
    # pins FastMCP(name) against a None/default substitution
    assert build_server(_FakeUC()).name == "pointlessql"  # type: ignore[arg-type]
    assert build_server(_FakeUC(), name="custom").name == "custom"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_server_exposes_the_read_only_catalog_tools() -> None:
    """All four browse tools are registered with descriptions."""
    server = build_server(_FakeUC())  # type: ignore[arg-type]
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}
    assert {
        "list_catalogs",
        "list_schemas",
        "list_tables",
        "describe_table",
        "get_lineage",
        "get_effective_permissions",
        "list_metric_views",
        "get_metric_view",
    } <= set(by_name)
    # every tool advertises a description so MCP clients can render it
    assert all(t.description for t in tools)


@pytest.mark.asyncio
async def test_tools_dispatch_into_the_facade() -> None:
    """Invoking a tool forwards its arguments to the UC facade verbatim."""
    fake = _FakeUC()
    server = build_server(fake)  # type: ignore[arg-type]

    await server.call_tool("list_catalogs", {})
    await server.call_tool(
        "describe_table", {"catalog": "main", "schema": "gold", "table": "orders"}
    )

    assert ("list_catalogs", ()) in fake.calls
    assert ("get_table", ("main", "gold", "orders")) in fake.calls


@pytest.mark.asyncio
async def test_lineage_and_metric_tools_dispatch_with_their_arguments() -> None:
    """The lineage, permissions, and metric-view tools forward their args."""
    fake = _FakeUC()
    server = build_server(fake)  # type: ignore[arg-type]

    await server.call_tool("get_lineage", {"full_name": "c.s.t", "depth": 2})
    await server.call_tool("get_lineage", {"full_name": "c.s.t"})  # default depth
    await server.call_tool(
        "get_effective_permissions", {"securable_type": "table", "full_name": "c.s.t"}
    )
    await server.call_tool("list_metric_views", {"catalog": "c", "schema": "s"})
    await server.call_tool("get_metric_view", {"full_name": "c.s.m"})

    assert ("get_lineage", ("c.s.t", 2)) in fake.calls
    assert ("get_lineage", ("c.s.t", 3)) in fake.calls  # the default depth is forwarded
    assert ("get_effective_permissions", ("table", "c.s.t")) in fake.calls
    assert ("list_metric_views", ("c", "s")) in fake.calls
    assert ("get_metric_view", ("c.s.m",)) in fake.calls


@pytest.mark.asyncio
async def test_describe_table_result_carries_facade_payload() -> None:
    """The tool result surfaces the table metadata the facade returned."""
    server = build_server(_FakeUC())  # type: ignore[arg-type]
    result = await server.call_tool(
        "describe_table", {"catalog": "c", "schema": "s", "table": "orders"}
    )
    assert "orders" in str(result)
