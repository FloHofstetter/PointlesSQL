"""``/api/data-products/trending`` + ``/data-products/trending`` (Phase 72.3).

Two endpoints:

* ``GET /api/data-products/trending`` — JSON list of the
  freshest cached trending rows.  ``workspace_scope='current'``
  (default) filters to the caller's workspace; ``='all'``
  requires an admin / auditor (Phase 34 cross-workspace
  precedent).
* ``GET /data-products/trending`` — HTML page rendering the
  same data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.services.data_products import fetch_trending

router = APIRouter(tags=["data-products"])


def _check_scope_gate(scope: str, request: Request) -> None:
    """Cross-workspace scope requires admin or auditor."""
    if scope != "all":
        return
    user = get_user(request)
    if user.get("is_admin") or user.get("is_auditor"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="cross-workspace-trending",
        securable_type="data_product",
        full_name="trending",
    )


@router.get("/api/data-products/trending")
async def get_data_products_trending(
    request: Request,
    workspace_scope: str = Query(default="current"),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Return cached trending rows."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    _check_scope_gate(workspace_scope, request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = fetch_trending(
            session,
            workspace_id=workspace_id,
            workspace_scope=workspace_scope,
            limit=limit,
        )
    return {"workspace_scope": workspace_scope, "trending": rows}


@router.get(
    "/data-products/trending",
    response_class=HTMLResponse,
    response_model=None,
)
async def data_products_trending_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the trending board HTML."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/data-products/trending", status_code=303
        )
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = fetch_trending(
            session,
            workspace_id=workspace_id,
            workspace_scope="current",
            limit=10,
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/data_products_trending.html",
        {
            "active_page": "data_products",
            "trending": rows,
            "can_cross_workspace": user["is_admin"] or user.get("is_auditor", False),
        },
    )
