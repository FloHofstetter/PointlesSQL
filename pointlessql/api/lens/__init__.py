"""HTTP routes for the Lens read-only Q&A surface.

Sub-routers (mounted in :mod:`pointlessql.api.main`):

* ``provenance``    — ``/api/lens/provenance`` GET.
* ``sessions``      — ``/api/lens/sessions`` CRUD.
* ``messages``      — ``/api/lens/sessions/{id}/messages`` SSE
                      .
* ``pinned``        — ``/api/lens/pinned`` CRUD.

Every sub-router gates on :func:`require_analyst` for read access;
mutations beyond pin/session-CRUD are not exposed (Lens is read-only
by charter).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import require_analyst
from pointlessql.api.lens.messages import router as _messages_router
from pointlessql.api.lens.pinned import router as _pinned_router
from pointlessql.api.lens.provenance import router as _provenance_router
from pointlessql.api.lens.sessions import router as _sessions_router

router = APIRouter(tags=["lens"])

_api_router = APIRouter(prefix="/api/lens")
_api_router.include_router(_provenance_router)
_api_router.include_router(_sessions_router)
_api_router.include_router(_messages_router)
_api_router.include_router(_pinned_router)
router.include_router(_api_router)


@router.get(
    "/lens",
    response_class=HTMLResponse,
    dependencies=[Depends(require_analyst)],
)
def lens_index_page(request: Request) -> HTMLResponse:
    """Render the Lens chat-UI landing page.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Server-rendered Jinja2 page; the chat dynamics live in the
        Alpine.js block inside ``pages/lens_index.html``.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/lens_index.html",
        {"active_page": "lens"},
    )


__all__ = ["router"]
