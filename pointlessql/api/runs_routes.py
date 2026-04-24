"""Agent-run supervision routes — stub surface for Phase 12.12.2.

Phase 12.12.2 introduces ``/runs`` as the human supervision page that
replaces the deleted browser notebook editor. Until Sprint 13.2 lands
the ``agent_runs`` Alembic table + executor, the list is empty by
construction — the page exists so the nav link ("Runs") has a
destination and so end-to-end pivot checks can assert a 200 here
instead of a 404.

Once Sprint 13.2 is in, this module grows a DB query against
``agent_runs`` and Sprint 13.4 ships the filter bar + detail route.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["runs"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


@router.get("/runs", response_class=HTMLResponse)
async def runs_list_page(request: Request) -> HTMLResponse:
    """Render the supervision list of agent runs (stub, empty list).

    The Sprint 13.4 rewrite will replace the stub with a sortable /
    filterable table backed by the ``agent_runs`` DB table. For now
    the page is an empty-state card so the nav entry has a landing
    spot.

    Args:
        request: Incoming FastAPI request; auth is enforced by the
            app-wide middleware, no per-route gate yet.

    Returns:
        The rendered ``pages/runs_list.html`` template with an empty
        ``runs`` list.
    """
    runs: list[dict[str, Any]] = []
    return _templates(request).TemplateResponse(
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
