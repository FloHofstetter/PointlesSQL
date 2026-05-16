"""HTML pages for the Ingest UI (Phase 82).

Three pages: the listing, the "new source" form, and the per-source
detail page.  All three gate on session login; the templates handle
the workspace-scoping by reading the same ``current_workspace_id``
context the API endpoints use.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.models import IngestSource
from pointlessql.models.ingest import INGEST_SOURCE_KINDS

router = APIRouter(tags=["ingest"])


@router.get("/ingest/sources", response_class=HTMLResponse, response_model=None)
async def ingest_sources_list(request: Request) -> HTMLResponse | RedirectResponse:
    """List the workspace's ingest sources."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/ingest/sources", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/ingest_sources_list.html",
        {
            "active_page": "ingest",
            "is_admin": user["is_admin"],
            "connector_kinds": INGEST_SOURCE_KINDS,
        },
    )


@router.get(
    "/ingest/sources/new", response_class=HTMLResponse, response_model=None
)
async def ingest_sources_new(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the connect-a-source form."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/ingest/sources/new", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/ingest_sources_new.html",
        {
            "active_page": "ingest",
            "is_admin": user["is_admin"],
            "connector_kinds": INGEST_SOURCE_KINDS,
        },
    )


@router.get(
    "/ingest/sources/{source_id}",
    response_class=HTMLResponse,
    response_model=None,
)
async def ingest_source_detail(
    request: Request, source_id: int
) -> HTMLResponse | RedirectResponse:
    """Render the per-source detail page.

    Args:
        request: Incoming FastAPI request.
        source_id: Primary key of the source.

    Returns:
        Detail page HTML, or 404 / login redirect when applicable.

    Raises:
        HTTPException: 404 when the source doesn't exist in the
            caller's workspace.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/ingest/sources/{source_id}", status_code=303
        )
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        if row is None or row.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="source not found")
        source_name = row.name
        source_kind = row.kind
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/ingest_source_detail.html",
        {
            "active_page": "ingest",
            "is_admin": user["is_admin"],
            "source_id": source_id,
            "source_name": source_name,
            "source_kind": source_kind,
        },
    )
