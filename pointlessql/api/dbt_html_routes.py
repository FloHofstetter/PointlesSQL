"""HTML page route for the dbt Pipelines tab.

Renders the iframe wrapper at ``/dbt`` whose target ``/dbt-docs/`` is
served by the reverse-proxy in :mod:`pointlessql.api.dbt_proxy`.  We
split the HTML wrapper from the proxy so the user lands inside the
standard PointlesSQL chrome (icon-rail + breadcrumbs + topbar) instead
of being dropped into a chrome-less dbt UI.

Like the MLflow tab, the page does not require admin scope — any
authenticated user can browse the dbt-docs surface.  Mutating actions
(e.g. ``dbt run``) live behind separate ``/api/dbt/...`` routes that
add their own scope checks.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user

router = APIRouter(tags=["dbt"])


@router.get("/dbt", response_class=HTMLResponse, response_model=None)
async def dbt_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the dbt Pipelines iframe wrapper page.

    Args:
        request: FastAPI request, used for auth + template context.

    Returns:
        HTMLResponse | RedirectResponse: The rendered page, or a
            redirect to the login page for anonymous users.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/dbt", status_code=303)

    templates = request.app.state.templates
    dbt_running = request.app.state.dbt_subprocess is not None

    return templates.TemplateResponse(
        request,
        "pages/dbt.html",
        {
            "active_page": "dbt",
            "active_section": "dbt",
            "dbt_running": dbt_running,
            "is_admin": user["is_admin"],
        },
    )
