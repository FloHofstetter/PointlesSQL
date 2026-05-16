"""HTML page for the ``/help`` reference (Phase 81.L)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user

router = APIRouter(tags=["help"])


@router.get("/help", response_class=HTMLResponse, response_model=None)
async def help_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render ``/help`` — the global keyboard + feature reference.

    Linked from the topbar ``?`` button.  Per-page help modals (e.g.
    the Feed shortcut sheet) remain the quick on-page reference;
    ``/help`` is the canonical index that covers every surface in
    one scrollable document.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/help", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/help.html",
        {"active_page": "help", "is_admin": user["is_admin"]},
    )
