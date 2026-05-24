"""Polymorphic reviews router (Phase 77.0.F.2 + 77.1.5 + 77.2.1).

The dispatcher delegates ``kind='dp'`` to the existing DP-scoped
service handlers (unchanged for behaviour parity) and any other
``supports_reviews=True`` kind to the polymorphic handlers added in
Phase 77.2.1.  Kinds with ``supports_reviews=False`` return 501.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.data_products_routes.reviews import (
    delete_data_product_review,
    list_data_product_reviews,
    upsert_data_product_review,
)
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    delete_polymorphic_review,
    list_polymorphic_reviews,
    upsert_polymorphic_review,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.services.social.entity_registry import get as registry_get

router = APIRouter(tags=["social"])


def _require_reviews_kind(kind: str) -> None:
    """Raise 501 when *kind* is not a reviews-supporting entity."""
    try:
        spec = registry_get(kind)
    except KeyError as exc:
        raise BadRequestError(f"unknown entity_kind: {kind!r}") from exc
    if not spec.supports_reviews:
        # bare-http-ok: 501 stays a raw HTTPException — "kind doesn't
        # support reviews" is a registry-level statement with no
        # domain-exception sibling.
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
    """Dispatch a reviews list by entity kind."""
    _require_reviews_kind(kind)
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_data_product_reviews(catalog, schema, request)
    resolved_ref = parse_ref(kind, ref)
    return await list_polymorphic_reviews(kind, resolved_ref, request)


@router.put("/api/social/{kind}/{ref:path}/reviews")
async def put_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch a review upsert by entity kind."""
    _require_reviews_kind(kind)
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        as_agent = request.query_params.get("as_agent")
        return await upsert_data_product_review(
            catalog, schema, request, as_agent=as_agent
        )
    resolved_ref = parse_ref(kind, ref)
    return await upsert_polymorphic_review(kind, resolved_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/reviews")
async def delete_social_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch a review DELETE by entity kind."""
    _require_reviews_kind(kind)
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await delete_data_product_review(catalog, schema, request)
    resolved_ref = parse_ref(kind, ref)
    return await delete_polymorphic_review(kind, resolved_ref, request)
