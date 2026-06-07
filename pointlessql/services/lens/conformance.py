"""Conformance checks for the MCP/Lens tool surface (scaffold).

Validates the *shape* of the tool surface — that each tool's spec is
internally consistent (write tools carry an op_name, mandate audit, and
require the author scope; read tools require the analyst scope) and that the
read registry and the spec table agree.  This is the static half of the
conformance suite; the dynamic half (driving the stdio + SSE protocol with
valid/invalid inputs and asserting schema + scope + provenance behaviour) is
a follow-up that builds on these checks.

Pure + import-light: it inspects specs and the existing read registry, with
no live server and no tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from pointlessql.services.lens.tools._spec import (
    SCOPE_AGENT_AUTHOR,
    SCOPE_ANALYST,
    ToolCategory,
    ToolSpec,
)


@dataclass(frozen=True)
class SpecIssue:
    """One conformance problem found in a tool spec.

    Attributes:
        tool: The offending tool name.
        problem: A human-readable description of the inconsistency.
    """

    tool: str
    problem: str


def check_spec(spec: ToolSpec) -> list[SpecIssue]:
    """Return the conformance issues for a single tool spec (empty if clean).

    Args:
        spec: The tool spec to validate.

    Returns:
        A list of :class:`SpecIssue`; empty when the spec is consistent.
    """
    issues: list[SpecIssue] = []
    if not spec.name:
        issues.append(SpecIssue(spec.name, "empty tool name"))
    if spec.category is ToolCategory.WRITE:
        if spec.op_name is None:
            issues.append(SpecIssue(spec.name, "write tool must declare an op_name"))
        if not spec.audit_mandatory:
            issues.append(SpecIssue(spec.name, "write tool must mandate audit"))
        if SCOPE_AGENT_AUTHOR not in spec.scope_required:
            issues.append(SpecIssue(spec.name, "write tool must require the agent_author scope"))
    else:
        if spec.op_name is not None:
            issues.append(SpecIssue(spec.name, "read tool must not declare an op_name"))
        if spec.audit_mandatory:
            issues.append(SpecIssue(spec.name, "read tool should not mandate audit"))
        if SCOPE_ANALYST not in spec.scope_required:
            issues.append(SpecIssue(spec.name, "read tool must require the analyst scope"))
    return issues


def check_specs(specs: list[ToolSpec]) -> list[SpecIssue]:
    """Return all conformance issues across *specs* plus duplicate-name checks.

    Args:
        specs: Every tool spec on the surface (read + write).

    Returns:
        The flattened list of issues; empty when the whole surface is clean.
    """
    issues: list[SpecIssue] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            issues.append(SpecIssue(spec.name, "duplicate tool name"))
        seen.add(spec.name)
        issues.extend(check_spec(spec))
    return issues
