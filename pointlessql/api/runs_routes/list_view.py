"""Run-supervision list views — HTML page + JSON sibling.

A newest-first overview of agent runs with drill-down links into
``/runs/{id}``.  Auth is enforced by app-wide middleware; the
template layers the filter bar and admin-only Approve / Deny column
on top.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.runs_routes._loaders import load_runs
from pointlessql.api.runs_routes._shared import templates

router = APIRouter()


@router.get("/runs", response_class=HTMLResponse)
async def runs_list_page(request: Request) -> HTMLResponse:
    """Render the supervision list of agent runs.

    Args:
        request: Incoming FastAPI request; auth is enforced by
            app-wide middleware.

    Returns:
        ``pages/runs_list.html`` populated with up to 200 runs.
    """
    runs = load_runs(request)
    return templates(request).TemplateResponse(
        request,
        "pages/runs_list.html",
        {
            "runs": runs,
            "active_page": "runs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/runs")
async def runs_list_api(request: Request) -> dict[str, Any]:
    """JSON sibling of ``GET /runs`` for machine consumers."""
    return {"runs": load_runs(request)}
