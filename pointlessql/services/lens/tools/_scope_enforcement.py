"""Scope enforcement for MCP/Lens tool invocations.

A single check, :func:`require_scopes`, that a tool executor calls before
doing anything: it raises when the caller's granted scopes do not cover the
tool's required scopes.  Keeping it here (rather than duplicated per tool)
means the write tools all gate access the same way, and the conformance
suite can assert the gate is present.

The granted scopes come from the caller's API key (the ``analyst`` /
``agent_author`` / ``agent_approver`` flags).  Resolving those flags from the
key onto the session context is the transport layer's job; this module only
compares two sets.
"""

from __future__ import annotations

from collections.abc import Iterable


class ToolScopeError(PermissionError):
    """Raised when a caller lacks a scope a tool requires."""


def require_scopes(granted: Iterable[str], required: Iterable[str], *, tool_name: str) -> None:
    """Assert *granted* covers every scope in *required*.

    Args:
        granted: Scope flags the caller holds (from their API key).
        required: Scope flags the tool requires (``ToolSpec.scope_required``).
        tool_name: The tool name, for the error message.

    Raises:
        ToolScopeError: If any required scope is missing.
    """
    missing = set(required) - set(granted)
    if missing:
        raise ToolScopeError(
            f"tool {tool_name!r} requires scope(s) {sorted(missing)} not held by the caller"
        )
