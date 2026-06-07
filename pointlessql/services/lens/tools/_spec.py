"""Tool specification + capability metadata for the MCP/Lens tool surface.

The existing read tools are plain :class:`ToolDef` entries.  As the surface
grows to include *governed writes*, each tool needs richer metadata than a
name + schema: what category it is (read vs write), which API-key scopes it
requires, whether it must record provenance, whether it is idempotent, and
whether it needs an approval gate before a destructive effect.

:class:`ToolSpec` carries that metadata.  It is pure data — no executor, no
imports of the live registry or server — so it can describe both the
existing read tools and the planned write tools, and drive the generated
tool-coverage matrix and the conformance suite without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# API-key scope flags that gate tool access.  ``analyst`` already exists on
# the ApiKey model for the read surface; ``agent_author`` / ``agent_approver``
# are the planned write/approval scopes (their ApiKey columns + migration are
# a follow-up — see the phase notes).
SCOPE_ANALYST = "analyst"
SCOPE_AGENT_AUTHOR = "agent_author"
SCOPE_AGENT_APPROVER = "agent_approver"


class ToolCategory(StrEnum):
    """Whether a tool only reads or can mutate state."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class ToolSpec:
    """Capability metadata for one tool on the MCP/Lens surface.

    Attributes:
        name: The tool name (matches the ``ToolDef.name`` for read tools).
        category: ``read`` or ``write``.
        description: One-line capability summary for the matrix + LLM.
        scope_required: API-key scope flags a caller must hold.
        audit_mandatory: Whether an invocation must persist provenance
            (always ``True`` for writes — no mutation without a trail).
        idempotent: Whether repeating the call with the same args is safe.
        approval_gate: Whether a destructive effect needs an approver
            (the ``agent_approver`` scope) before it runs.
        op_name: The :class:`~pointlessql.types.OpName` value the write
            records under, or ``None`` for read tools.
    """

    name: str
    category: ToolCategory
    description: str
    scope_required: tuple[str, ...] = ()
    audit_mandatory: bool = False
    idempotent: bool = True
    approval_gate: bool = False
    op_name: str | None = None


def read_spec(name: str, description: str) -> ToolSpec:
    """Build a :class:`ToolSpec` for a read-only tool (analyst scope)."""
    return ToolSpec(
        name=name,
        category=ToolCategory.READ,
        description=description,
        scope_required=(SCOPE_ANALYST,),
        audit_mandatory=False,
        idempotent=True,
        approval_gate=False,
        op_name=None,
    )


def write_spec(
    name: str,
    description: str,
    *,
    op_name: str,
    idempotent: bool = False,
    approval_gate: bool = False,
    extra_scopes: tuple[str, ...] = (),
) -> ToolSpec:
    """Build a :class:`ToolSpec` for a governed write tool.

    Write tools always require the ``agent_author`` scope and always record
    provenance; destructive ones additionally set an approval gate.

    Args:
        name: Tool name.
        description: One-line capability summary.
        op_name: The :class:`~pointlessql.types.OpName` value to record under.
        idempotent: Whether re-running with the same args is safe.
        approval_gate: Whether the effect needs an approver first.
        extra_scopes: Additional required scope flags.

    Returns:
        The write-tool :class:`ToolSpec`.
    """
    scopes = (SCOPE_AGENT_AUTHOR, *extra_scopes)
    if approval_gate:
        scopes = (*scopes, SCOPE_AGENT_APPROVER)
    return ToolSpec(
        name=name,
        category=ToolCategory.WRITE,
        description=description,
        scope_required=scopes,
        audit_mandatory=True,
        idempotent=idempotent,
        approval_gate=approval_gate,
        op_name=op_name,
    )
