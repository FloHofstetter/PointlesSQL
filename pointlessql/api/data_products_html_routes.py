"""HTML pages for the data-product browse + detail surface.

Two pages mirror the Phase-21 ``/models`` shape:

* ``GET /data-products`` — index with a card per cached product.
* ``GET /data-products/{catalog}/{schema}`` — detail page with six
  tabs (Overview / Contract / Diff / Lineage / Compliance /
  Discussion — the latter added in Phase 71.1) backed by the JSON
  routes in :mod:`pointlessql.api.data_products_routes`.

Both redirect anonymous visitors to ``/auth/login?next=...`` so the
deep-link survives the OIDC round-trip.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.data_products_routes import _load_one  # pyright: ignore[reportPrivateUsage]
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.models.catalog._data_products import DataProduct

router = APIRouter(tags=["data-products"])


@router.get("/data-products", response_class=HTMLResponse, response_model=None)
async def data_products_index_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the workspace-wide data-product index page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/data-products", status_code=303
        )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/data_products.html",
        {
            "active_page": "data_products",
            "is_admin": user["is_admin"],
        },
    )


@router.get(
    "/data-products/followed",
    response_class=HTMLResponse,
    response_model=None,
)
async def data_products_followed_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the per-user "Followed products" index (Phase 71.3).

    Lists every data product the logged-in user has followed in
    their current workspace, sorted by ``last_loaded_at`` desc.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/data-products/followed", status_code=303
        )

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.execute(
            select(DataProduct, DataProductFollow)
            .join(
                DataProductFollow,
                (DataProductFollow.data_product_id == DataProduct.id)
                & (DataProductFollow.workspace_id == DataProduct.workspace_id),
            )
            .where(
                DataProductFollow.workspace_id == workspace_id,
                DataProductFollow.user_id == user["id"],
            )
            .order_by(DataProduct.last_loaded_at.desc())
        ).all()
    followed = [
        {
            "catalog": dp.catalog_name,
            "schema": dp.schema_name,
            "ref": f"{dp.catalog_name}.{dp.schema_name}",
            "version": dp.version,
            "last_loaded_at": dp.last_loaded_at.isoformat(),
            "followed_at": follow.created_at.isoformat(),
        }
        for dp, follow in rows
    ]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/data_products_followed.html",
        {
            "active_page": "data_products",
            "followed": followed,
        },
    )


@router.get(
    "/data-products/{catalog}/{schema}",
    response_class=HTMLResponse,
    response_model=None,
)
async def data_product_detail_page(
    catalog: str,
    schema: str,
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the per-product detail page (5 tabs).

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Either the detail page or a redirect to ``/auth/login``
        when the visitor is anonymous.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/data-products/{catalog}/{schema}",
            status_code=303,
        )

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, contract, steward_email, steward_display = _load_one(
        factory, workspace_id, catalog, schema
    )

    is_steward = (
        row.steward_user_id is not None and row.steward_user_id == user["id"]
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/data_product.html",
        {
            "active_page": "data_products",
            "is_admin": user["id"] != 0 and user["is_admin"],
            "current_user_id": user["id"],
            "is_steward": is_steward,
            "product": {
                "id": row.id,
                "catalog": row.catalog_name,
                "schema": row.schema_name,
                "ref": f"{row.catalog_name}.{row.schema_name}",
                "name": contract.name,
                "version": row.version,
                "description": row.description,
                "sla_minutes": row.sla_minutes,
                "steward_email": steward_email,
                "steward_display_name": steward_display,
                "last_loaded_at": row.last_loaded_at.isoformat(),
            },
        },
    )
