"""Admin surface for contextual agent guardrails.

Authoring of the underlying Cedar modules lives on the policy-modules
page; this surface is the *agent-action* lens on them — an evaluation
console that turns the model / MCP-service / tool / content-flag
dimensions into a verdict (allow / require-approval / deny) so authors
can see how a contextual guardrail will fire before it gates a real run.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    require_admin,
)
from pointlessql.services import policy_as_code as policy_service

router = APIRouter(tags=["admin-agent-guardrails"])


@router.get("/admin/agent-guardrails", response_class=HTMLResponse)
async def admin_agent_guardrails_index(request: Request) -> HTMLResponse:
    """Render the contextual-guardrail evaluation console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_agent_guardrails.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_agent_guardrails.html",
        {
            "active_page": "admin",
            "content_flags": list(policy_service.GUARDRAIL_CONTENT_FLAGS),
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.post("/api/admin/agent-guardrails/evaluate")
async def evaluate_agent_guardrail(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Evaluate a hypothetical agent action against the workspace guardrails.

    Args:
        request: Incoming FastAPI request.
        body: JSON with optional ``principal_id`` (int), ``model``,
            ``mcp_service``, ``tool`` (strings) and a ``content_flags``
            object of ``{flag: bool}``.

    Returns:
        The verdict payload from
        :func:`policy_as_code.evaluate_agent_action`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)

    principal_raw = body.get("principal_id")
    principal_id: int | None = None
    if isinstance(principal_raw, int):
        principal_id = principal_raw
    elif isinstance(principal_raw, str) and principal_raw.strip().isdigit():
        principal_id = int(principal_raw.strip())

    flags_raw = body.get("content_flags")
    content_flags: dict[str, bool] = {}
    if isinstance(flags_raw, dict):
        flags_dict = cast("dict[str, Any]", flags_raw)
        for flag in policy_service.GUARDRAIL_CONTENT_FLAGS:
            content_flags[flag] = bool(flags_dict.get(flag))

    return policy_service.evaluate_agent_action(
        factory,
        workspace_id=workspace_id,
        principal_id=principal_id,
        model=_clean(body.get("model")),
        mcp_service=_clean(body.get("mcp_service")),
        tool=_clean(body.get("tool")),
        content_flags=content_flags,
    )


def _clean(value: Any) -> str | None:
    """Return a trimmed non-empty string, or ``None``.

    Args:
        value: Raw request-body field.

    Returns:
        The stripped string when it is a non-empty ``str``, else ``None``.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
