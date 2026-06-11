"""Delta Sharing HTML pages — provider admin + consumer browser.

Two HTML routes over the JSON surface in
:mod:`pointlessql.api.sharing_routes`:

* ``/admin/sharing`` — admin-gated provider administration (shares,
  share objects, recipient grants, one-time recipient tokens).
* ``/shared-with-me`` — any signed-in user's view of *remote*
  providers: register a profile, browse its shares and tables, and
  preview rows over the open protocol.

Both pages load their data client-side through ``/api/sharing``;
the routes only render the chrome.

NOTE: this router is intentionally **not registered** yet.  The
navigation integration wires it into
``pointlessql/api/_bootstrap/_routers.py`` next to the
``sharing_routes`` JSON router (``app.include_router(...)``).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin

router = APIRouter(tags=["sharing-html"])


@router.get("/admin/sharing", response_class=HTMLResponse)
async def admin_sharing_page(request: Request):
    """Render the provider-side Delta Sharing cockpit (shares + recipients)."""
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_sharing.html",
        {"active_page": "admin"},
    )


@router.get("/shared-with-me", response_class=HTMLResponse)
async def shared_with_me_page(request: Request):
    """Render the consumer-side browser for remote Delta Sharing providers."""
    return get_templates(request).TemplateResponse(
        request,
        "pages/shared_with_me.html",
        {"active_page": "shared-with-me"},
    )
