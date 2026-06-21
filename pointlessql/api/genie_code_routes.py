"""Genie Code command center — the unified agentic-authoring hub.

A full-page roof over the agentic-authoring surfaces PointlesSQL already
ships (NL→SQL, NL→notebook, pipeline canvas, ingest, jobs, agent runs,
ML).  The page renders the authoring entry points plus a cross-surface
glance at recent supervised agent runs.  Read-only: it links out to each
surface and summarises run state.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
)
from pointlessql.services import genie_code

router = APIRouter(tags=["genie-code"])


@router.get("/genie-code", response_class=HTMLResponse)
async def genie_code_page(request: Request) -> HTMLResponse:
    """Render the Genie Code agentic-authoring command center.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/genie_code.html`` response.
    """
    return get_templates(request).TemplateResponse(
        request,
        "pages/genie_code.html",
        {
            "active_page": "genie-code",
            "active_section": "genie-code",
            "surfaces": genie_code.authoring_surfaces(),
        },
    )


@router.get("/api/genie-code/overview")
async def genie_code_overview(request: Request) -> dict[str, Any]:
    """Return the authoring registry + recent agent-run glance.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The overview payload from
        :func:`genie_code.command_center_overview`.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return genie_code.command_center_overview(factory, workspace_id=workspace_id)
