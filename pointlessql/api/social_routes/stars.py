"""Polymorphic star bookmark router.

Stars are the lightweight "I bookmarked this" primitive — separate
from Follow (which signals "I want notifications").  Three
endpoints sit under the polymorphic
``/api/social/{kind}/{ref:path}/star`` namespace, plus a profile
endpoint at ``/api/users/{user_id}/stars`` for the Phase-77.10
"Starred" profile tab.

For ``kind='dp'`` we route to the same polymorphic handler — the
social_targets row is resolved kind-agnostically, so DP stars land
in the same ``social_stars`` table.  No legacy DP star handler
exists (the pre-77.8 component was localStorage-only), so there's
no kind dispatch needed inside this router.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    get_polymorphic_star,
    list_user_stars,
    star_polymorphic_entity,
    unstar_polymorphic_entity,
)

router = APIRouter(tags=["social"])


def _normalised_ref(kind: str, ref: str) -> str:
    """Validate ``(kind, ref)`` regardless of DP vs polymorphic dispatch.

    The polymorphic ``social_stars`` table is kind-agnostic from
    day 1, so DP stars land in the same table as table / model /
    branch / run stars.  We still funnel DP refs through
    :func:`parse_dp_ref` so the ``catalog.schema`` shape is enforced
    upfront; for every other kind :func:`parse_ref` runs the
    kind-specific shape check.
    """
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return f"{catalog}.{schema}"
    return parse_ref(kind, ref)


@router.get("/api/social/{kind}/{ref:path}/star")
async def get_star(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Return ``{"starred": bool, "count": int}`` for the caller."""
    canonical_ref = _normalised_ref(kind, ref)
    return await get_polymorphic_star(kind, canonical_ref, request)


@router.post("/api/social/{kind}/{ref:path}/star")
async def post_star(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Idempotently bookmark the polymorphic entity."""
    canonical_ref = _normalised_ref(kind, ref)
    return await star_polymorphic_entity(kind, canonical_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/star")
async def delete_star(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Idempotently drop the caller's bookmark on this entity."""
    canonical_ref = _normalised_ref(kind, ref)
    return await unstar_polymorphic_entity(kind, canonical_ref, request)


@router.get("/api/users/{user_id}/stars")
async def get_user_stars(
    user_id: int,
    request: Request,
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List a user's starred entities (admin or self only).

    Feeds the Phase-77.10 ``/users/{id}`` "Starred" profile tab.
    """
    return await list_user_stars(user_id, request, kind=kind, limit=limit)
