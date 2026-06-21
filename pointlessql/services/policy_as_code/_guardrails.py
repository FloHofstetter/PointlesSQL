"""Contextual service policies — guardrail evaluation for agent actions.

The Cedar engine answers a binary permit/forbid question.  An agent
guardrail needs a third outcome: *allow with human approval*.  This
module layers that trichotomy on top of the existing engine without
changing it, by evaluating an agent action against two Cedar action
verbs:

* ``Action::"agent_action"`` — the direct request.
* ``Action::"agent_action_with_approval"`` — the same request as it
  would arrive *after* a human approves it.

The mapping is then:

* no guardrail modules linked → ``allow`` (guardrails are opt-in);
* the direct action permits → ``allow``;
* the direct action forbids but the with-approval action permits →
  ``require_approval``;
* both forbid → ``deny`` (and fail-closed errors land here too).

A policy author writes contextual guardrails by referencing the agent
context attributes this module feeds in — ``context.model``,
``context.mcp_service``, ``context.tool`` and the boolean content flags
in :data:`GUARDRAIL_CONTENT_FLAGS` — e.g. *forbid* ``agent_action`` when
``context.unsafe_content == true`` for a hard block, or *permit*
``agent_action_with_approval`` when ``context.model == "grok"`` to route
that model through review.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.policy_as_code._engine import cedar_evaluate
from pointlessql.services.policy_as_code._loader import load_active_modules_for_workspace
from pointlessql.services.policy_as_code._translator import (
    build_resource_id,
    cedar_action,
    principal_uid,
)
from pointlessql.types import SessionFactory

#: Boolean content-inspection flags a caller (or the console) can raise
#: on an agent action so guardrail policies can gate on them.
GUARDRAIL_CONTENT_FLAGS: tuple[str, ...] = (
    "pii",
    "prompt_injection",
    "jailbreak",
    "unsafe_content",
)

VERDICT_ALLOW = "allow"
VERDICT_REQUIRE_APPROVAL = "require_approval"
VERDICT_DENY = "deny"

_AGENT_ACTION = cedar_action("agent_action")
_AGENT_ACTION_WITH_APPROVAL = cedar_action("agent_action_with_approval")


def evaluate_agent_action(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    principal_id: int | None,
    model: str | None = None,
    mcp_service: str | None = None,
    tool: str | None = None,
    content_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Evaluate one agent action against the workspace's guardrails.

    Builds the Cedar context from the agent dimensions, evaluates the
    direct and with-approval actions against every enabled module in the
    workspace, and collapses the two decisions into an allow / deny /
    require-approval verdict (see the module docstring for the rule).

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose enabled modules form the guardrails.
        principal_id: Acting user id, or ``None`` for an anonymous agent.
        model: Foundation-model name the agent is using (e.g. ``grok``).
        mcp_service: MCP service the action targets, if any.
        tool: Tool name being invoked, if any.
        content_flags: Subset of :data:`GUARDRAIL_CONTENT_FLAGS` set to
            ``True``; unknown keys are ignored, missing ones default off.

    Returns:
        A JSON-safe dict with ``verdict``, the governing Cedar ``effect``,
        ``empty`` (no guardrails configured), ``latency_ms``,
        ``error_class``, ``diagnostics`` and the evaluated ``context`` /
        ``principal`` / ``resource`` so the caller can show its work.
    """
    flags = content_flags or {}
    context: dict[str, Any] = {
        "model": model or "",
        "mcp_service": mcp_service or "",
        "tool": tool or "",
    }
    for key in GUARDRAIL_CONTENT_FLAGS:
        context[key] = bool(flags.get(key, False))

    modules = load_active_modules_for_workspace(session_factory, workspace_id=workspace_id)
    principal = principal_uid({"id": principal_id} if principal_id is not None else None)
    resource = build_resource_id(
        resource_type="AgentAction",
        id_value=f"{mcp_service or 'unknown'}:{tool or 'unknown'}",
    )

    primary = cedar_evaluate(
        modules,
        principal=principal,
        action=_AGENT_ACTION,
        resource=resource,
        context=context,
    )
    if primary.empty or primary.effect == "permit":
        verdict, governing = VERDICT_ALLOW, primary
    else:
        approval = cedar_evaluate(
            modules,
            principal=principal,
            action=_AGENT_ACTION_WITH_APPROVAL,
            resource=resource,
            context=context,
        )
        if approval.effect == "permit":
            verdict, governing = VERDICT_REQUIRE_APPROVAL, approval
        else:
            verdict, governing = VERDICT_DENY, primary

    return {
        "verdict": verdict,
        "effect": governing.effect,
        "empty": primary.empty,
        "latency_ms": governing.latency_ms,
        "error_class": governing.error_class,
        "diagnostics": governing.diagnostics,
        "context": context,
        "principal": principal,
        "resource": resource,
    }
