"""``GET /api/data-products`` — list every cached product in workspace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.data_products_routes._shared import serialise_product
from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products")
async def list_data_products(request: Request) -> dict[str, Any]:
    """Return every cached data product in the active workspace.

    Each row is enriched with the Phase-71.2 ``avg_stars`` +
    ``review_count`` aggregate so the browse-page cards (and the
    Phase-71.6 sortable table) can render the star badge without
    a follow-up call per product.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"workspace_id": int, "data_products": [...]}`` ordered by
        catalog/schema name.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    items: list[dict[str, Any]] = []
    with factory() as session:
        rows = (
            session.execute(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .order_by(DataProduct.catalog_name, DataProduct.schema_name)
            )
            .scalars()
            .all()
        )
        steward_ids = [r.steward_user_id for r in rows if r.steward_user_id is not None]
        steward_map: dict[int, tuple[str, str]] = {}
        if steward_ids:
            users = (
                session.execute(select(User).where(User.id.in_(steward_ids)))
                .scalars()
                .all()
            )
            steward_map = {u.id: (u.email, u.display_name) for u in users}

        dp_ids = [r.id for r in rows]
        review_agg: dict[int, tuple[float | None, int]] = {}
        if dp_ids:
            agg_rows = session.execute(
                select(
                    DataProductReview.data_product_id,
                    func.avg(DataProductReview.stars),
                    func.count(DataProductReview.id),
                )
                .where(
                    DataProductReview.workspace_id == workspace_id,
                    DataProductReview.data_product_id.in_(dp_ids),
                )
                .group_by(DataProductReview.data_product_id)
            ).all()
            review_agg = {
                int(dp_id): (float(avg) if avg is not None else None, int(cnt))
                for dp_id, avg, cnt in agg_rows
            }

        for row in rows:
            email, display = (
                steward_map.get(row.steward_user_id, (None, None))
                if row.steward_user_id is not None
                else (None, None)
            )
            payload = serialise_product(
                row,
                steward_email=email,
                steward_display_name=display,
            )
            avg, count = review_agg.get(row.id, (None, 0))
            payload["avg_stars"] = avg
            payload["review_count"] = count
            items.append(payload)

    return {"workspace_id": workspace_id, "data_products": items}
