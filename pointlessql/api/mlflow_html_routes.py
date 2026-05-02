"""HTML page route for the MLflow Tracking tab (Phase 21.0).

Single-route module that renders the iframe wrapper page at ``/ml``.
The iframe target ``/mlflow/`` is served by the reverse-proxy in
:mod:`pointlessql.api.mlflow_proxy`. We split the HTML wrapper from
the proxy so the user lands inside the standard PointlesSQL chrome
(icon-rail + breadcrumbs + topbar) instead of being dropped into a
chrome-less MLflow UI.

The route is intentionally not gated to admin-only — any
authenticated user can use the MLflow UI through the iframe; the
same auth gate runs again on every proxied request.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_user

router = APIRouter(tags=["mlflow"])


@router.get("/ml", response_class=HTMLResponse, response_model=None)
async def mlflow_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the MLflow iframe wrapper page.

    Args:
        request: FastAPI request, used for the auth check + template
            context.

    Returns:
        HTMLResponse | RedirectResponse: The rendered ML tab, or a
            redirect to ``/auth/login?next=/ml`` for anonymous users.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/ml", status_code=303)

    templates = request.app.state.templates
    mlflow_running = request.app.state.mlflow_subprocess is not None

    return templates.TemplateResponse(
        request,
        "pages/mlflow.html",
        {
            "active_page": "mlflow",
            "mlflow_running": mlflow_running,
            "is_admin": user["is_admin"],
        },
    )
