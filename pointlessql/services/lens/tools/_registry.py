"""Concrete tool registry — the single source of truth for ALL_TOOLS.

Modifications: add a new tool by importing it here and appending its
:class:`ToolDef` to :data:`ALL_TOOLS`.  Both transports (browser
chat-loop and MCP server) iterate this list verbatim.
"""

from __future__ import annotations

from pointlessql.services.lens.tools._base import ToolDef
from pointlessql.services.lens.tools.catalog import (
    DESCRIBE_TABLE_TOOL,
    LIST_CATALOGS_TOOL,
    LIST_SCHEMAS_TOOL,
    LIST_TABLES_TOOL,
)
from pointlessql.services.lens.tools.lineage import (
    LINEAGE_NEIGHBORS_TOOL,
    PROVENANCE_TOOL,
)

ALL_TOOLS: list[ToolDef] = [
    LIST_CATALOGS_TOOL,
    LIST_SCHEMAS_TOOL,
    LIST_TABLES_TOOL,
    DESCRIBE_TABLE_TOOL,
    LINEAGE_NEIGHBORS_TOOL,
    PROVENANCE_TOOL,
]
"""Authoritative ordered list of every Lens tool.

Order is preserved when serialising provider schemas (some LLMs
weight earlier-listed tools slightly more in tool-choice selection).
Provenance + catalog are listed first because they are the primary
analyst entry points.
"""


def get_tool(name: str) -> ToolDef | None:
    """Return the :class:`ToolDef` registered under *name*, or ``None``."""
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None


def list_tool_names() -> list[str]:
    """Return every registered tool name in registry order."""
    return [tool.name for tool in ALL_TOOLS]
