"""Provenance wrapper for governed MCP write tools.

The load-bearing invariant of the agent write surface: **no MCP mutation
without an ``AgentRunOperation`` + CloudEvent** — the exact same provenance
chain a human write goes through.  :func:`execute_write_with_provenance`
enforces it: a write tool body only runs inside an ``operation_context``
bound to a real agent run, so the operation row is always emitted (success
or failure) and the run id is mandatory.

This is the gate between "an LLM asked to write" and "a write happened with
an attributable, audited trail".  Concrete write executors call it; they do
not call ``operation_context`` directly, so the invariant lives in one place.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from pointlessql.services.lens.tools._scope_enforcement import require_scopes

if TYPE_CHECKING:
    from pointlessql.services.agent_runs.operations._common import OperationRecorder
    from pointlessql.services.lens.tools._base import SessionContext
    from pointlessql.services.lens.tools._spec import ToolSpec


class WriteProvenanceError(RuntimeError):
    """Raised when a governed write cannot establish its provenance."""


async def execute_write_with_provenance(
    ctx: SessionContext,
    spec: ToolSpec,
    *,
    agent_run_id: str | None,
    granted_scopes: set[str],
    params: dict[str, Any],
    target_table: str | None,
    body: Callable[[OperationRecorder], Awaitable[Any]],
) -> Any:
    """Run a write *body* inside the audited agent-run provenance chain.

    Enforces, in order: the tool's required scopes (``require_scopes``
    raises :class:`ToolScopeError` for a missing scope), the presence
    of an agent run (no anonymous mutation), and an
    ``operation_context`` that persists an ``AgentRunOperation`` row
    whether the body succeeds or raises.

    Args:
        ctx: The per-call session context (factory, workspace, uc client).
        spec: The write tool's spec (scopes, op_name).
        agent_run_id: The owning agent run; **required** — a write with no
            run has no provenance and is refused.
        granted_scopes: Scope flags the caller holds.
        params: Operation params recorded on the trail row.
        target_table: The mutated table, if known up front.
        body: The async mutation, receiving the live recorder to annotate.

    Returns:
        Whatever *body* returns.

    Raises:
        WriteProvenanceError: If *agent_run_id* / *op_name* is missing.
    """
    require_scopes(granted_scopes, spec.scope_required, tool_name=spec.name)
    if not agent_run_id:
        raise WriteProvenanceError(
            f"write tool {spec.name!r} requires an agent_run_id — no MCP mutation "
            "may run without an attributable agent-run provenance trail"
        )
    if spec.op_name is None:
        raise WriteProvenanceError(f"write tool {spec.name!r} has no op_name to record under")

    from pointlessql.services.agent_runs import operation_context
    from pointlessql.types import OpName, RunId

    with operation_context(
        ctx.factory,
        agent_run_id=RunId(agent_run_id),
        op_name=OpName(spec.op_name),
        params=params,
        target_table=target_table,
    ) as recorder:
        return await body(recorder)
