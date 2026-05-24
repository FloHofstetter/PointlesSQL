"""``GET /admin/sources`` — system-wide ingest health monitor."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin

router = APIRouter(tags=["admin"])


@router.get("/admin/sources", response_class=HTMLResponse)
async def admin_ingest_sources_index(request: Request) -> HTMLResponse:
    """Render the system-wide ingest health monitor.

    Pure HTML shell — the page fetches ``/api/admin/ingest-sources``
    on load to populate the table.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_sources.html",
        {
            "active_page": "admin",
            "is_admin": True,
        },
    )
