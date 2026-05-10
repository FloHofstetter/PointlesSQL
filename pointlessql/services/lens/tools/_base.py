"""Base types for the Lens tool registry.

Three Pydantic-friendly primitives:

* :class:`SessionContext` — the per-call context passed to every tool
  executor.  Holds workspace + user + factory + uc_client so the
  executor doesn't need to know about FastAPI ``request.state``.
* :class:`ToolDef` — the registry entry shape: name + description +
  input / output Pydantic models + async executor.
* :func:`to_openai_schemas` / :func:`to_anthropic_schemas` /
  :func:`to_mcp_schemas` — provider-specific schema converters.

The tool authors only deal with their input/output models and the
executor coroutine; transports import :data:`ALL_TOOLS` and route
calls through :func:`execute_tool_with_audit`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.config import Settings
    from pointlessql.services.unitycatalog import UnityCatalogClient


class LensToolError(Exception):
    """Wraps any executor-internal exception with tool context.

    Carries enough metadata for the audit-hook to write a
    ``tool_status='error'`` row without the chat-loop having to
    parse the original traceback.

    Lives in ``_base`` (not ``_audit_hook``) so tool modules can
    raise it without forming a circular import via the registry.
    """

    def __init__(
        self,
        *,
        tool_name: str,
        message: str,
        status: str = "error",
        tool_args: object | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.status = status


class UnknownLensToolError(LensToolError):
    """Raised when ``execute_tool_with_audit`` is asked for a tool not in registry."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            tool_name=tool_name,
            message=f"Unknown Lens tool {tool_name!r}",
            status="error",
        )


@dataclass(frozen=True)
class SessionContext:
    """Per-tool-call context.

    Attributes:
        workspace_id: Active workspace id.  Tools must not read or
            write outside this workspace.
        user_id: User id of the analyst, or ``None`` for API-key /
            MCP callers.
        lens_session_id: Owning Lens session id.  ``None`` for
            stateless invocations (e.g. a smoke test).
        factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.
        uc_client: Async UC client wired with the analyst principal,
            or ``None`` when the chat-loop is in test mode and tools
            should fall back to no-op responses.
    """

    workspace_id: int
    user_id: int | None
    lens_session_id: int | None
    factory: sessionmaker[Session]
    settings: Settings
    uc_client: UnityCatalogClient | None


@dataclass(frozen=True)
class ToolDef:
    """One Lens tool entry in :data:`ALL_TOOLS`.

    Attributes:
        name: Tool name (lowercase snake_case, ≤ 64 chars).  Surfaces
            as the ``function.name`` / ``tool.name`` in provider
            schemas.
        description: One-paragraph LLM-facing description.  This is
            what the LLM sees when deciding whether to invoke the
            tool.  Be specific about what the tool does and what
            *not* to use it for (e.g. "use this to count rows; use
            ``query`` for arbitrary SELECT").
        input_model: Pydantic model class for the input args.
        output_model: Pydantic model class for the output payload.
        executor: Async callable ``(ctx, args) -> result``.  Receives
            the validated input model instance; returns an output
            model instance.
    """

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    executor: Callable[[SessionContext, Any], Awaitable[Any]]


def _input_schema(tool: ToolDef) -> dict[str, Any]:
    """Return the JSON-schema for the tool's input model."""
    return tool.input_model.model_json_schema()


def to_openai_schemas(tools: list[ToolDef]) -> list[dict[str, Any]]:
    """Convert a list of :class:`ToolDef` to OpenAI function-calling format.

    Args:
        tools: The tool defs to convert.

    Returns:
        A list of ``{"type": "function", "function": {...}}`` dicts
        suitable for ``openai.chat.completions.create(tools=...)``.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": _input_schema(tool),
            },
        }
        for tool in tools
    ]


def to_anthropic_schemas(tools: list[ToolDef]) -> list[dict[str, Any]]:
    """Convert a list of :class:`ToolDef` to Anthropic ``tools=`` format.

    Args:
        tools: The tool defs to convert.

    Returns:
        A list of ``{"name", "description", "input_schema"}`` dicts
        suitable for ``anthropic.messages.create(tools=...)``.
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": _input_schema(tool),
        }
        for tool in tools
    ]


def to_mcp_schemas(tools: list[ToolDef]) -> list[dict[str, Any]]:
    """Convert a list of :class:`ToolDef` to MCP ``tools/list`` shape.

    Args:
        tools: The tool defs to convert.

    Returns:
        A list of ``{"name", "description", "inputSchema"}`` dicts
        per the MCP 2025-03 schema.
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": _input_schema(tool),
        }
        for tool in tools
    ]
