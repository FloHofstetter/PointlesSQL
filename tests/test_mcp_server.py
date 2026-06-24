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


@pytest.mark.asyncio
async def test_server_exposes_the_read_only_catalog_tools() -> None:
    """All four browse tools are registered with descriptions."""
    server = build_server(_FakeUC())  # type: ignore[arg-type]
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}
    assert {"list_catalogs", "list_schemas", "list_tables", "describe_table"} <= set(by_name)
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
async def test_describe_table_result_carries_facade_payload() -> None:
    """The tool result surfaces the table metadata the facade returned."""
    server = build_server(_FakeUC())  # type: ignore[arg-type]
    result = await server.call_tool(
        "describe_table", {"catalog": "c", "schema": "s", "table": "orders"}
    )
    assert "orders" in str(result)
