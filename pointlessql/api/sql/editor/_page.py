"""``GET /sql`` — the editor's Jinja2 page.

Single HTML route kept in its own module so the rest of the editor
package stays clear of template + Jinja imports.
"""

from __future__ import annotations

import uuid

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
            # Phase 91 — surface the chat-drawer feature flag + a
            # fresh editor session id per render so the WS route has
            # a stable handle across reload of the same tab via
            # sessionStorage.
            "chat_enabled": settings.sql_chat.enabled,
            "editor_session_id": str(uuid.uuid4()),
            "active_page": "sql",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
