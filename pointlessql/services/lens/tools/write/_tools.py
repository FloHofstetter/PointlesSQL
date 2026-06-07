"""Governed write tools for the MCP/Lens surface (skeletons).

Defines the write tools' specs, input/output schemas, and executors.  Every
executor routes through :func:`execute_write_with_provenance`, so the scope
check and the mandatory ``AgentRunOperation`` trail are wired in.  The actual
lakehouse mutation is intentionally **not** performed yet: the executor body
raises :class:`WriteToolNotEnabledError` so the contract, scopes, and
provenance wrapper are complete and reviewable, while the effecting calls
(PQL write / Delta branch ops through the UC client) land behind a security
review and a live-verification pass.

These tools are deliberately **not** registered into the live ``ALL_TOOLS``
read-only registry; wiring them in (gated on the ``agent_author`` scope) is a
follow-up so the running read-only MCP server is never destabilised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from pointlessql.services.lens.tools._spec import ToolSpec, write_spec
from pointlessql.services.lens.tools.write._provenance import execute_write_with_provenance

if TYPE_CHECKING:
    from pointlessql.services.lens.tools._base import SessionContext


class WriteToolNotEnabledError(NotImplementedError):
    """Raised by a skeleton write executor whose effecting call is deferred."""


# --- schemas ---------------------------------------------------------------


class WriteTableArgs(BaseModel):
    """Arguments for ``pql_write_table``."""

    table: str = Field(description="Fully-qualified target table (catalog.schema.table).")
    mode: Literal["append", "overwrite", "merge"] = Field(description="Delta write mode.")
    merge_keys: list[str] = Field(default_factory=list, description="Keys for mode='merge'.")
    data_csv: str = Field(description="Inline CSV of the rows to write.")


class WriteResult(BaseModel):
    """Result of a write tool."""

    target_table: str
    delta_version_before: int | None = None
    delta_version_after: int | None = None
    rows_affected: int = 0


class BranchArgs(BaseModel):
    """Arguments for the branch write tools."""

    table: str = Field(description="Fully-qualified table the branch is on.")
    branch: str = Field(description="Branch name.")
    source_version: int | None = Field(default=None, description="Source version for promote.")


class BranchResult(BaseModel):
    """Result of a branch write tool."""

    table: str
    branch: str
    status: str


# --- specs -----------------------------------------------------------------

WRITE_TABLE_SPEC: ToolSpec = write_spec(
    "pql_write_table",
    "Append / overwrite / merge rows into a Delta table (destructive — needs approval).",
    op_name="write_table",
    idempotent=False,
    approval_gate=True,
)
BRANCH_CREATE_SPEC: ToolSpec = write_spec(
    "pql_branch_create",
    "Create a Delta branch (tag) on a table.",
    op_name="branch_create",
    idempotent=True,
)
BRANCH_PROMOTE_SPEC: ToolSpec = write_spec(
    "pql_branch_promote",
    "Promote a Delta branch into the table's main timeline (destructive — needs approval).",
    op_name="branch_promote",
    idempotent=False,
    approval_gate=True,
)
BRANCH_DISCARD_SPEC: ToolSpec = write_spec(
    "pql_branch_discard",
    "Discard a Delta branch (destructive — needs approval).",
    op_name="branch_discard",
    idempotent=True,
    approval_gate=True,
)

WRITE_TOOL_SPECS: tuple[ToolSpec, ...] = (
    WRITE_TABLE_SPEC,
    BRANCH_CREATE_SPEC,
    BRANCH_PROMOTE_SPEC,
    BRANCH_DISCARD_SPEC,
)


# --- executors (skeletons routed through provenance) -----------------------


async def _deferred_mutation(spec: ToolSpec) -> Any:
    """Raise — the effecting mutation is gated behind a security review."""
    raise WriteToolNotEnabledError(
        f"{spec.name}: provenance + scope gating is wired, but the effecting "
        "lakehouse mutation is deferred pending security review + live verification"
    )


async def execute_write_table(
    ctx: SessionContext,
    args: WriteTableArgs,
    *,
    agent_run_id: str | None,
    granted_scopes: set[str],
) -> WriteResult:
    """Write rows into a Delta table through the provenance chain (skeleton)."""

    async def _body(_recorder: Any) -> WriteResult:
        return await _deferred_mutation(WRITE_TABLE_SPEC)

    return await execute_write_with_provenance(
        ctx,
        WRITE_TABLE_SPEC,
        agent_run_id=agent_run_id,
        granted_scopes=granted_scopes,
        params={"mode": args.mode, "merge_keys": args.merge_keys},
        target_table=args.table,
        body=_body,
    )


async def execute_branch_op(
    ctx: SessionContext,
    spec: ToolSpec,
    args: BranchArgs,
    *,
    agent_run_id: str | None,
    granted_scopes: set[str],
) -> BranchResult:
    """Run a branch create/promote/discard through the provenance chain (skeleton)."""

    async def _body(_recorder: Any) -> BranchResult:
        return await _deferred_mutation(spec)

    return await execute_write_with_provenance(
        ctx,
        spec,
        agent_run_id=agent_run_id,
        granted_scopes=granted_scopes,
        params={"branch": args.branch, "source_version": args.source_version},
        target_table=args.table,
        body=_body,
    )
