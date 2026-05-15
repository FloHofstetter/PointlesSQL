"""Polymorphic reviews router (Phase 77.0.F.2 + 77.1.5 dispatch).

Reviews (star ratings) stay DP-only for now per the entity-registry
``supports_reviews`` flag — tables / branches set ``False``.  Any
non-DP kind returns a clean 501 with a pointer at the registry flag.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.data_products_routes.reviews import (
    delete_data_product_review,
    list_data_product_reviews,
    upsert_data_product_review,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref
from pointlessql.services.social.entity_registry import get as registry_get

router = APIRouter(tags=["social"])


def _require_reviews_kind(kind: str) -> None:
    """Raise 501 when *kind* is not a reviews-supporting entity."""
    try:
        spec = registry_get(kind)
    except KeyError as exc:
        # bare-http-ok: surface unknown kinds as 400 here too.
        raise HTTPException(
            status_code=400, detail=f"unknown entity_kind: {kind!r}"
        ) from exc
    if not spec.supports_reviews:
        # bare-http-ok: reviews are entity-kind opt-in.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} does not support reviews "
                "(supports_reviews=False in the entity registry)"
            ),
        )


@router.get("/api/social/{kind}/{ref:path}/reviews")
async def list_social_reviews(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch a reviews list by entity kind (DP only this phase)."""
    _require_reviews_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_data_product_reviews(catalog, schema, request)


@router.put("/api/social/{kind}/{ref:path}/reviews")
async def put_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch a review upsert by entity kind (DP only this phase)."""
    _require_reviews_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    as_agent = request.query_params.get("as_agent")
    return await upsert_data_product_review(
        catalog, schema, request, as_agent=as_agent
    )


@router.delete("/api/social/{kind}/{ref:path}/reviews")
async def delete_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch a review DELETE by entity kind (DP only this phase)."""
    _require_reviews_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await delete_data_product_review(catalog, schema, request)
