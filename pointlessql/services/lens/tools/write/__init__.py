"""Governed write tools for the MCP/Lens agent surface.

Re-export facade.  The write tools extend the read-only Lens surface with
mutations that go through the same provenance + audit chain humans do (no
mutation without an ``AgentRunOperation``).  They are **not** registered into
the live ``ALL_TOOLS`` read-only registry yet — wiring them in, gated on the
``agent_author`` scope, is a follow-up so the running MCP server stays
read-only and stable until the write executors are reviewed and verified.
"""

from __future__ import annotations

from pointlessql.services.lens.tools.write._provenance import (
    WriteProvenanceError,
    execute_write_with_provenance,
)
from pointlessql.services.lens.tools.write._tools import (
    WRITE_TOOL_SPECS,
    BranchArgs,
    BranchResult,
    WriteResult,
    WriteTableArgs,
    WriteToolNotEnabledError,
    execute_branch_op,
    execute_write_table,
)

__all__ = [
    "WRITE_TOOL_SPECS",
    "BranchArgs",
    "BranchResult",
    "WriteProvenanceError",
    "WriteResult",
    "WriteTableArgs",
    "WriteToolNotEnabledError",
    "execute_branch_op",
    "execute_write_table",
    "execute_write_with_provenance",
]
