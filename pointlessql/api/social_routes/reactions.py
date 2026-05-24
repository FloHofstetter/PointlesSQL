"""Polymorphic reactions router.

For ``kind='dp'`` the call delegates to the existing DP reaction
handlers so that the legacy fan-out + audit prefix semantics
stay intact.  For every other kind the entity-level **and**
comment-level reaction endpoints route to the polymorphic
handlers landed (entity) and Phase 78 polish
(comment).  ``data_product_comment_reactions`` is already
polymorphic-safe — it keys on ``comment_id`` — so the unlock
is purely a routing change.
"""

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
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    apply_polymorphic_comment_reaction,
    apply_polymorphic_reaction,
    list_polymorphic_comment_reactions,
    list_polymorphic_reactions,
    remove_polymorphic_comment_reaction,
    remove_polymorphic_reaction,
)

router = APIRouter(tags=["social"])


@router.post("/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions")
async def add_social_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction POST polymorphically."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await add_comment_reaction(catalog, schema, comment_id, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await apply_polymorphic_comment_reaction(kind, polymorphic_ref, comment_id, request)


@router.delete("/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions/{emoji}")
async def remove_social_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction DELETE polymorphically."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await remove_comment_reaction(catalog, schema, comment_id, emoji, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await remove_polymorphic_comment_reaction(
        kind, polymorphic_ref, comment_id, emoji, request
    )


@router.get("/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions")
async def list_social_comment_reactions(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction list polymorphically."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_comment_reactions(catalog, schema, comment_id, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_comment_reactions(kind, polymorphic_ref, comment_id, request)


@router.post("/api/social/{kind}/{ref:path}/reactions")
async def add_social_entity_reaction(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch an entity-level reaction POST by kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await add_dp_reaction(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await apply_polymorphic_reaction(kind, polymorphic_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/reactions/{emoji}")
async def remove_social_entity_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction DELETE by kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await remove_dp_reaction(catalog, schema, emoji, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await remove_polymorphic_reaction(kind, polymorphic_ref, emoji, request)


@router.get("/api/social/{kind}/{ref:path}/reactions")
async def list_social_entity_reactions(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch an entity-level reaction list by kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_dp_reactions(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_reactions(kind, polymorphic_ref, request)
