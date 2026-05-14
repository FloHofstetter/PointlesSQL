"""Polymorphic reviews router (Phase 77.0.F.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.reviews import (
    delete_data_product_review,
    list_data_product_reviews,
    upsert_data_product_review,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/reviews")
async def list_social_reviews(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP review list handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_data_product_reviews(catalog, schema, request)


@router.put("/api/social/{kind}/{ref:path}/reviews")
async def put_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP review upsert handler for ``kind='dp'``.

    Re-extracts the ``?as_agent=`` query param from the request so
    the speak-as-agent path (Phase 76.5.1) survives the indirection.
    """
    catalog, schema = parse_dp_ref(kind, ref)
    as_agent = request.query_params.get("as_agent")
    return await upsert_data_product_review(
        catalog, schema, request, as_agent=as_agent
    )


@router.delete("/api/social/{kind}/{ref:path}/reviews")
async def delete_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP review delete handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await delete_data_product_review(catalog, schema, request)
