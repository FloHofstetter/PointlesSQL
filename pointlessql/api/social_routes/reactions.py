"""Polymorphic reactions router (Phase 77.0.F.2 + 77.1.5 dispatch).

Reactions stay DP-only this phase — the underlying handlers do a
DP-coupled lookup that 77.1.5 doesn't generalise.  Phase 77.8
extends the table to polymorphic anchors alongside the Stars +
polymorphic-follow work.  Non-DP kinds get a clean 501.
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
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


def _require_dp_kind(kind: str) -> None:
    """Raise 501 when *kind* is not ``'dp'`` (reactions stay DP-only)."""
    if kind != "dp":
        # bare-http-ok: deferred per locked decision.
        raise HTTPException(
            status_code=501,
            detail=(
                f"reactions for kind={kind!r} are deferred to "
                "Phase 77.8 (polymorphic reactions land alongside Stars)"
            ),
        )


@router.post(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions"
)
async def add_social_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction POST (DP only this phase)."""
    _require_dp_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await add_comment_reaction(catalog, schema, comment_id, request)


@router.delete(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/reactions/{emoji}"
)
async def remove_social_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch a comment-reaction DELETE (DP only this phase)."""
    _require_dp_kind(kind)
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
    _require_dp_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_comment_reactions(
        catalog, schema, comment_id, request
    )


@router.post("/api/social/{kind}/{ref:path}/reactions")
async def add_social_entity_reaction(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction POST (DP only this phase)."""
    _require_dp_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await add_dp_reaction(catalog, schema, request)


@router.delete("/api/social/{kind}/{ref:path}/reactions/{emoji}")
async def remove_social_entity_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction DELETE (DP only this phase)."""
    _require_dp_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await remove_dp_reaction(catalog, schema, emoji, request)


@router.get("/api/social/{kind}/{ref:path}/reactions")
async def list_social_entity_reactions(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Dispatch an entity-level reaction list (DP only this phase)."""
    _require_dp_kind(kind)
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_dp_reactions(catalog, schema, request)
