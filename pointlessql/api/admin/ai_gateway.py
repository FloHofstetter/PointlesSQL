"""Admin surface for the AI-spend governance overlay.

A unified AI-gateway lens over the Lens chat spend: it rolls the
metered model round-trips up by provider, model, and user, splits the
spend into model-inference versus tool / SQL cost, and evaluates the
accrued spend against a budget the admin types in.  The per-session
cost gate already enforces hard runtime caps; this surface is the
cross-session visibility + attribution layer.

The console is read-only — it derives every number from turns the
chat-loop already persisted and never mutates a session.
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
from pointlessql.services import ai_gateway

router = APIRouter(tags=["admin-ai-gateway"])


@router.get("/admin/ai-gateway", response_class=HTMLResponse)
async def admin_ai_gateway_index(request: Request) -> HTMLResponse:
    """Render the AI-spend governance console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_ai_gateway.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_ai_gateway.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/ai-gateway/overview")
async def ai_gateway_overview(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound on a turn"),
    budget: str | None = Query(default=None, description="Spend ceiling to evaluate against"),
) -> dict[str, Any]:
    """Return the AI-spend overlay for the workspace's Lens sessions.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on a turn's ``created_at``;
            unparseable values are ignored (span all turns).
        budget: Spend ceiling to evaluate accrued cost against; blank
            or non-numeric values skip the budget verdict.

    Returns:
        The overlay payload from :func:`ai_gateway.ai_spend_overview`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return ai_gateway.ai_spend_overview(
        factory,
        workspace_id=workspace_id,
        since=parse_since(since),
        budget=parse_budget(budget),
    )
