"""HTML page route for the agent command center."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.command_center_routes._shared import build_command_center
from pointlessql.api.dependencies import get_templates

router = APIRouter()


@router.get("/command-center", response_class=HTMLResponse)
async def command_center_page(request: Request) -> HTMLResponse:
    """Render the cockpit over in-flight runs and candidate sets.

    Read-only supervision: any authenticated user can watch, while the
    Approve / Deny actions on the cards defer to the admin-gated
    ``/api/agent-runs/{id}/approve|deny`` endpoints.  ``active_page`` is
    ``runs`` so the page nests under the Watch hub alongside ``/runs``.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/command_center.html`` response.
    """
    data = build_command_center(request)
    ctx: dict[str, Any] = {
        "live": data["live"],
        "candidate_groups": data["candidate_groups"],
        "counts": data["counts"],
        "active_page": "runs",
        "active_catalog": None,
        "active_schema": None,
        "active_table": None,
    }
    return get_templates(request).TemplateResponse(request, "pages/command_center.html", ctx)
