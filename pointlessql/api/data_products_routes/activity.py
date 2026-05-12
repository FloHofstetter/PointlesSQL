"""``/api/data-products/{catalog}/{schema}/activity`` — merged feed (Phase 72.1)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.services.data_products import fetch_activity_for_dp

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/activity")
async def get_data_product_activity(
    catalog: str,
    schema: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return the merged activity feed for one data product.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        limit: Max rows returned (server cap 200).
        offset: Pagination offset (post-merge, so the four streams
            are merged then paginated together).

    Returns:
        ``{"data_product_id": int, "activity": [...]}`` rows in
        newest-first order.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = fetch_activity_for_dp(
            session,
            workspace_id=workspace_id,
            dp=row,
            limit=limit,
            offset=offset,
        )
    return {
        "data_product_id": row.id,
        "activity": [asdict(r) for r in rows],
    }
