"""Polymorphic follows router (Phase 77.0.F.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.follows import (
    follow_data_product,
    get_followers_count,
    list_followers,
    unfollow_data_product,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.post("/api/social/{kind}/{ref:path}/follow")
async def follow_social_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP follow handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await follow_data_product(catalog, schema, request)


@router.delete("/api/social/{kind}/{ref:path}/follow")
async def unfollow_social_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP unfollow handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await unfollow_data_product(catalog, schema, request)


@router.get("/api/social/{kind}/{ref:path}/followers/count")
async def get_social_followers_count(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP follower-count handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await get_followers_count(catalog, schema, request)


@router.get("/api/social/{kind}/{ref:path}/followers")
async def list_social_followers(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP follower-list handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_followers(catalog, schema, request)
