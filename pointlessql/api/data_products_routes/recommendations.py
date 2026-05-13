"""``/api/data-products/.../related`` + ``/recommendations`` (Phase 73.5).

Two endpoints:

* ``GET /api/data-products/{catalog}/{schema}/related`` — top-N
  related DPs for one source DP, read from the cooccurrence
  cache.
* ``GET /api/data-products/recommendations`` — per-user
  "Recommended for you" list (union of related-to-followed
  minus already-followed).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.services.data_products import (
    fetch_recommendations_for_user,
    fetch_related,
)

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/related")
async def get_related(
    catalog: str,
    schema: str,
    request: Request,
    limit: int = Query(default=5, ge=1, le=50),
) -> dict[str, Any]:
    """Return the top-N related DPs for one source DP.

    Args:
        catalog: UC catalog segment of the source DP.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        limit: Max related rows.

    Returns:
        ``{"data_product_id": int, "related": [...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        related = fetch_related(
            session,
            workspace_id=workspace_id,
            data_product_id=row.id,
            limit=limit,
        )
    return {"data_product_id": row.id, "related": related}


@router.get("/api/data-products/recommendations")
async def get_recommendations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Return the caller's "Recommended for you" entries.

    Args:
        request: Incoming FastAPI request.
        limit: Max rows.

    Returns:
        ``{"recommendations": [...]}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = fetch_recommendations_for_user(
            session,
            workspace_id=workspace_id,
            user_id=user["id"],
            limit=limit,
        )
    return {"recommendations": rows}
