"""``GET /sql`` — the editor's Jinja2 page.

Single HTML route kept in its own module so the rest of the editor
package stays clear of template + Jinja imports.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates
from pointlessql.config import Settings

router = APIRouter(tags=["sql"])


@router.get("/sql", response_class=HTMLResponse)
async def sql_editor_page(request: Request) -> HTMLResponse:
    """Render the SQL editor page."""
    settings: Settings = request.app.state.settings
    return get_templates(request).TemplateResponse(
        request,
        "pages/sql_editor.html",
        {
            "sql_enabled": settings.sql.enabled,
            "active_page": "sql",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
