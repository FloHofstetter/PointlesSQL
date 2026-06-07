---
title: MCP / Lens tool-coverage matrix (generated)
audience: contributor
---

# MCP / Lens tool-coverage matrix

**Generated** by `scripts/mcp_tool_matrix_generate.py` — do not hand-edit; regenerate after changing tools.

Tools: 11 (7 read, 4 write). Write tools are defined and provenance-gated but **not yet registered** into the live read-only server — their effecting mutations are deferred pending security review (see the phase notes).

| Tool | Category | Scopes | Audit | Idempotent | Approval | Op |
| --- | --- | --- | --- | --- | --- | --- |
| `describe_table` | read | analyst | — | ✓ | — | — |
| `lineage_neighbors` | read | analyst | — | ✓ | — | — |
| `list_catalogs` | read | analyst | — | ✓ | — | — |
| `list_schemas` | read | analyst | — | ✓ | — | — |
| `list_tables` | read | analyst | — | ✓ | — | — |
| `provenance` | read | analyst | — | ✓ | — | — |
| `query` | read | analyst | — | ✓ | — | — |
| `pql_branch_create` | write | agent_author | ✓ | ✓ | — | branch_create |
| `pql_branch_discard` | write | agent_author, agent_approver | ✓ | ✓ | ✓ | branch_discard |
| `pql_branch_promote` | write | agent_author, agent_approver | ✓ | — | ✓ | branch_promote |
| `pql_write_table` | write | agent_author, agent_approver | ✓ | — | ✓ | write_table |
