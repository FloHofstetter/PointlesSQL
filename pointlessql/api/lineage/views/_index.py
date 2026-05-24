"""Lineage explorer landing page — ``GET /lineage``."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates

router = APIRouter(tags=["lineage"])


@router.get("/lineage", response_class=HTMLResponse)
async def lineage_index_page(request: Request) -> HTMLResponse:
    """Render the Lineage explorer index.

    Standalone landing page surfacing the three primary lineage
    actions (trace a row, trace a column, browse recent traces).
    The two trace forms POST-redirect into the existing per-row /
    per-column trace pages, so no new API surface is needed.

    Recent traces are read client-side from
    ``localStorage["pql.recentTraces"]`` so the page is fully
    static server-side; the Alpine factory in the template hydrates
    it after first paint.

    Args:
        request: Starlette request used to look up the templates
            environment and thread the standard user / workspace
            context.

    Returns:
        ``HTMLResponse`` with the rendered explorer page.
    """
    return get_templates(request).TemplateResponse(
        request,
        "pages/lineage_index.html",
        {
            "active_page": "lineage",
        },
    )
