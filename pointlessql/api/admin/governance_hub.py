"""Admin surface for the governance hub.

A unified command center that rolls the workspace's scattered governance
signals — compliance-scanner findings and agent-run anomalies — into one
posture score and a severity-ranked remediation queue, so a steward sees
the whole surface and what to fix first without visiting each console.

Read-only: it aggregates findings other subsystems already wrote.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.admin._filters import parse_since
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    require_admin,
)
from pointlessql.services import governance_hub

router = APIRouter(tags=["admin-governance-hub"])


@router.get("/admin/governance-hub", response_class=HTMLResponse)
async def admin_governance_hub_index(request: Request) -> HTMLResponse:
    """Render the governance-hub command center.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_governance_hub.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_governance_hub.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/governance-hub/posture")
async def governance_hub_posture(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound on findings"),
) -> dict[str, Any]:
    """Return the workspace's posture score + remediation queue.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on a finding's timestamp;
            unparseable values are ignored (span all findings).

    Returns:
        The posture payload from
        :func:`governance_hub.governance_posture`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return governance_hub.governance_posture(
        factory,
        workspace_id=workspace_id,
        since=parse_since(since),
    )
