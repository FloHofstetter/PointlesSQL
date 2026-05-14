"""Polymorphic reactions router (Phase 77.0.F.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.reactions import (
    add_comment_reaction,
    add_dp_reaction,
    list_comment_reactions,
    list_dp_reactions,
    remove_comment_reaction,
    remove_dp_reaction,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.post(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions"
)
async def add_social_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment-reaction POST handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await add_comment_reaction(catalog, schema, comment_id, request)


@router.delete(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions/{emoji}"
)
async def remove_social_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment-reaction DELETE handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await remove_comment_reaction(
        catalog, schema, comment_id, emoji, request
    )


@router.get(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions"
)
async def list_social_comment_reactions(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment-reaction list handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_comment_reactions(
        catalog, schema, comment_id, request
    )


@router.post("/api/social/{kind}/{ref:path}/reactions")
async def add_social_entity_reaction(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP-level reaction POST handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await add_dp_reaction(catalog, schema, request)


@router.delete("/api/social/{kind}/{ref:path}/reactions/{emoji}")
async def remove_social_entity_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP-level reaction DELETE handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await remove_dp_reaction(catalog, schema, emoji, request)


@router.get("/api/social/{kind}/{ref:path}/reactions")
async def list_social_entity_reactions(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP-level reaction list handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_dp_reactions(catalog, schema, request)
