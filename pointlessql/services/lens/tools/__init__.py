"""Lens tool registry — single source of truth for both transports.

Browser chat-loop and MCP server both
consume :data:`ALL_TOOLS` and serialise it through provider-specific
schema converters.  Adding a new tool: write the executor + Pydantic
input/output models in a sub-module, append the :class:`ToolDef` to
:data:`ALL_TOOLS`.

Audit-trail: every tool dispatch goes through
:func:`execute_tool_with_audit`, which writes a ``lens_messages`` row
(role='tool') with the args + result + cost so the conversation
transcript carries an inline forensic record.
"""

from __future__ import annotations

from pointlessql.services.lens.tools._audit_hook import execute_tool_with_audit
from pointlessql.services.lens.tools._base import (
    LensToolError,
    SessionContext,
    ToolDef,
    UnknownLensToolError,
    to_anthropic_schemas,
    to_mcp_schemas,
    to_openai_schemas,
)
from pointlessql.services.lens.tools._registry import (
    ALL_TOOLS,
    get_tool,
    list_tool_names,
)

__all__ = [
    "ALL_TOOLS",
    "LensToolError",
    "SessionContext",
    "ToolDef",
    "UnknownLensToolError",
    "execute_tool_with_audit",
    "get_tool",
    "list_tool_names",
    "to_anthropic_schemas",
    "to_mcp_schemas",
    "to_openai_schemas",
]
