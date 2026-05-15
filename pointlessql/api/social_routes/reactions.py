"""Polymorphic reactions router (Phase 77.0.F.2 + 77.1.5 + 77.8.D dispatch).

For ``kind='dp'`` the call delegates to the existing DP reaction
handlers.  For non-DP kinds the entity-level reaction endpoints
route to the polymorphic handlers landed in Phase 77.8.D
(``data_product_reactions`` carries a polymorphic UNIQUE on
``(social_target_id, user_id, emoji)`` since 77.8.C).  Comment-
reactions stay DP-only this phase — the underlying comment-reaction
table is keyed by ``comment_id`` which is already polymorphic-safe;
the open work item is wiring the route to look up the comment row
without a DP context.  Deferred to 77.11.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

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
    apply_polymorphic_reaction,
    list_polymorphic_reactions,
    remove_polymorphic_reaction,
)

router = APIRouter(tags=["social"])


def _require_dp_kind_for_comment_reactions(kind: str) -> None:
    """Raise 501 when *kind* is not ``'dp'`` (comment reactions stay DP-only)."""
    if kind != "dp":
        # bare-http-ok: comment-reaction polymorphism is deferred.
        raise HTTPException(
            status_code=501,
            detail=(
                f"comment reactions for kind={kind!r} are deferred to "
                "Phase 77.11 — the underlying table is polymorphic-safe "
                "but the route still needs a DP context"
            ),
        )


@router.post(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions"
)
async def add_social_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction POST (DP only this phase)."""
    _require_dp_kind_for_comment_reactions(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await add_comment_reaction(catalog, schema, comment_id, request)


@router.delete(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions/{emoji}"
)
async def remove_social_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction DELETE (DP only this phase)."""
    _require_dp_kind_for_comment_reactions(kind)
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
    """Dispatch a comment-reaction list (DP only this phase)."""
    _require_dp_kind_for_comment_reactions(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_comment_reactions(
        catalog, schema, comment_id, request
    )


@router.post("/api/social/{kind}/{ref:path}/reactions")
async def add_social_entity_reaction(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction POST by kind (Phase 77.8.D)."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await add_dp_reaction(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await apply_polymorphic_reaction(kind, polymorphic_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/reactions/{emoji}")
async def remove_social_entity_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction DELETE by kind (Phase 77.8.D)."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await remove_dp_reaction(catalog, schema, emoji, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await remove_polymorphic_reaction(
        kind, polymorphic_ref, emoji, request
    )


@router.get("/api/social/{kind}/{ref:path}/reactions")
async def list_social_entity_reactions(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction list by kind (Phase 77.8.D)."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_dp_reactions(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_reactions(kind, polymorphic_ref, request)
