"""HTML page render for the visual Data-Product canvas editor.

One route: ``GET /dp/{dp_id}/canvas`` renders the standalone
full-screen Rete.js-based block-and-wire editor.  Lives in its own
module because the editor is a top-level page rather than a tab
inside the existing data-product detail surface, so wiring it
through ``data_products_html_routes.py`` would mix two unrelated URL
families (browsing vs authoring).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DataProduct

router = APIRouter(tags=["data-products"])


@router.get(
    "/dp/{dp_id}/canvas",
    response_class=HTMLResponse,
    response_model=None,
)
async def dp_canvas_editor_page(
    request: Request, dp_id: int
) -> HTMLResponse | RedirectResponse:
    """Render the visual canvas editor for *dp_id*.

    Anonymous visitors are redirected through the OIDC login so the
    deep-link survives the round-trip.  Unknown / cross-workspace
    ids surface as a :class:`ResourceNotFoundError` (404 via the
    centralised error handler).

    Args:
        request: Incoming FastAPI request.
        dp_id: ``DataProduct.id`` of the product to author.

    Returns:
        The rendered ``pages/dp_canvas_editor.html`` template, or a
        303 redirect to ``/auth/login?next=…`` for anonymous callers.

    Raises:
        ResourceNotFoundError: When *dp_id* is unknown to the active
            workspace.
    """  # noqa: DOC502
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/dp/{dp_id}/canvas", status_code=303
        )

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(DataProduct, dp_id)
        if row is None or row.workspace_id != workspace_id:
            raise ResourceNotFoundError(f"data product id={dp_id} not found")
        product = {
            "id": row.id,
            "catalog": row.catalog_name,
            "schema": row.schema_name,
            "ref": f"{row.catalog_name}.{row.schema_name}",
            "version": row.version,
            "description": row.description,
            "steward_user_id": row.steward_user_id,
        }

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/dp_canvas_editor.html",
        {
            "product": product,
            "current_user_id": int(user.get("id") or 0),
            "is_admin": bool(user.get("is_admin")),
            "is_steward": (
                product["steward_user_id"] is not None
                and product["steward_user_id"] == user["id"]
            ),
            "active_page": "data_products",
        },
    )
