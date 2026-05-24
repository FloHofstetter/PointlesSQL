"""Polymorphic follows router.

For ``kind='dp'`` the call delegates to the existing DP follow
handlers.  For non-DP kinds the follow / unfollow endpoints return
501 (the composite-PK constraint on ``data_product_follows``
blocks polymorphic writes); the count + list endpoints return
empty placeholders so the UI doesn't need a kind switch.  The
polymorphic follow table lands .
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.follows import (
    follow_data_product,
    get_followers_count,
    list_followers,
    unfollow_data_product,
)
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    follow_polymorphic_entity,
    get_polymorphic_followers_count,
    list_polymorphic_followers,
    unfollow_polymorphic_entity,
)

router = APIRouter(tags=["social"])


@router.post("/api/social/{kind}/{ref:path}/follow")
async def follow_social_entity(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a follow POST by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await follow_data_product(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await follow_polymorphic_entity(kind, polymorphic_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/follow")
async def unfollow_social_entity(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch an unfollow by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await unfollow_data_product(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await unfollow_polymorphic_entity(kind, polymorphic_ref, request)


@router.get("/api/social/{kind}/{ref:path}/followers/count")
async def get_social_followers_count(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a followers-count GET by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await get_followers_count(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await get_polymorphic_followers_count(kind, polymorphic_ref, request)


@router.get("/api/social/{kind}/{ref:path}/followers")
async def list_social_followers(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a followers-list GET by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_followers(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_followers(kind, polymorphic_ref, request)
