"""Admin surface for the agent-gateway governance overlay.

An AI-Gateway-style lens over the read-only agent-run supervision: it
rolls supervised runs up by harness and principal, surfaces the spend
telemetry per group, and evaluates the accrued spend against a budget
the admin types in.  Authoring of the contextual guardrails that gate a
single action lives on the agent-guardrails console; this surface is the
fleet-wide spend + telemetry view across runs.

The console is read-only — it derives every number from runs the
runtime already registered and never mutates one.  Live enforcement
(routing, mid-run blocking) stays in the runtime.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.admin._filters import parse_budget, parse_since
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    require_admin,
)
from pointlessql.services import agent_gateway

router = APIRouter(tags=["admin-agent-gateway"])


@router.get("/admin/agent-gateway", response_class=HTMLResponse)
async def admin_agent_gateway_index(request: Request) -> HTMLResponse:
    """Render the agent-gateway governance console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_agent_gateway.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_agent_gateway.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/agent-gateway/overview")
async def agent_gateway_overview(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
    budget: str | None = Query(default=None, description="Spend ceiling to evaluate against"),
) -> dict[str, Any]:
    """Return the spend + telemetry overlay for the workspace's runs.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on ``started_at``; out-of-range or
            unparseable values are ignored (span all runs).
        budget: Spend ceiling to evaluate accrued cost against; blank or
            non-numeric values skip the budget verdict.

    Returns:
        The overlay payload from
        :func:`agent_gateway.gateway_overview`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return agent_gateway.gateway_overview(
        factory,
        workspace_id=workspace_id,
        since=parse_since(since),
        budget=parse_budget(budget),
    )
