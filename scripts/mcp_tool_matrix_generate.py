"""Generate the versioned MCP/Lens tool-coverage matrix.

Combines the live read-tool registry (``ALL_TOOLS``) with the governed
write-tool specs into a single table — name, category, required scopes,
audit/idempotent/approval flags, op_name — and writes
``docs/internal/mcp-tool-matrix.md``.  Runs the static conformance checks
and refuses to write an inconsistent matrix (so spec drift is caught).

Run after adding or changing tools and commit the regenerated matrix:

    uv run python scripts/mcp_tool_matrix_generate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pointlessql.services.lens.conformance import check_specs
from pointlessql.services.lens.tools._registry import ALL_TOOLS
from pointlessql.services.lens.tools._spec import ToolSpec, read_spec
from pointlessql.services.lens.tools.write import WRITE_TOOL_SPECS


def all_specs() -> list[ToolSpec]:
    """Return read specs (derived from ALL_TOOLS) + the write specs."""
    read = [read_spec(tool.name, tool.description.split("\n", 1)[0]) for tool in ALL_TOOLS]
    return [*read, *WRITE_TOOL_SPECS]


def _flag(value: bool) -> str:
    """Render a bool as a check / dash for the table."""
    return "✓" if value else "—"


def render_markdown(specs: list[ToolSpec]) -> str:
    """Render the tool specs as the coverage-matrix Markdown document."""
    read_n = sum(1 for s in specs if s.category.value == "read")
    write_n = sum(1 for s in specs if s.category.value == "write")
    lines = [
        "---",
        "title: MCP / Lens tool-coverage matrix (generated)",
        "audience: contributor",
        "---",
        "",
        "# MCP / Lens tool-coverage matrix",
        "",
        "**Generated** by `scripts/mcp_tool_matrix_generate.py` — do not "
        "hand-edit; regenerate after changing tools.",
        "",
        f"Tools: {len(specs)} ({read_n} read, {write_n} write). Write tools are "
        "defined and provenance-gated but **not yet registered** into the live "
        "read-only server — their effecting mutations are deferred pending "
        "security review (see the phase notes).",
        "",
        "| Tool | Category | Scopes | Audit | Idempotent | Approval | Op |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for spec in sorted(specs, key=lambda s: (s.category.value, s.name)):
        lines.append(
            f"| `{spec.name}` | {spec.category.value} | "
            f"{', '.join(spec.scope_required) or '—'} | {_flag(spec.audit_mandatory)} | "
            f"{_flag(spec.idempotent)} | {_flag(spec.approval_gate)} | "
            f"{spec.op_name or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Generate the matrix, failing on any conformance issue."""
    specs = all_specs()
    issues = check_specs(specs)
    if issues:
        for issue in issues:
            print(f"conformance issue: {issue.tool}: {issue.problem}", file=sys.stderr)
        raise SystemExit(1)
    out = Path(__file__).resolve().parent.parent / "docs" / "internal" / "mcp-tool-matrix.md"
    out.write_text(render_markdown(specs), encoding="utf-8")
    print(f"wrote {out} — {len(specs)} tools, 0 conformance issues")


if __name__ == "__main__":
    main()
