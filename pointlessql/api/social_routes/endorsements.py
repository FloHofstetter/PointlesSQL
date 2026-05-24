"""Polymorphic endorsements router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.endorsements import (
    apply_endorsement,
    list_endorsements,
    remove_endorsement,
)
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    apply_polymorphic_endorsement,
    list_polymorphic_endorsements,
    remove_polymorphic_endorsement,
)

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/endorsements")
async def list_social_endorsements(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch an endorsement list by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_endorsements(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_endorsements(kind, polymorphic_ref, request)


@router.post("/api/social/{kind}/{ref:path}/endorsements")
async def apply_social_endorsement(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch an endorsement POST by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        as_agent = request.query_params.get("as_agent")
        return await apply_endorsement(catalog, schema, request, as_agent=as_agent)
    polymorphic_ref = parse_ref(kind, ref)
    return await apply_polymorphic_endorsement(kind, polymorphic_ref, request)


@router.delete("/api/social/{kind}/{ref:path}/endorsements/{endorsement_id}")
async def remove_social_endorsement(
    kind: str, ref: str, endorsement_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch an endorsement soft-delete by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await remove_endorsement(catalog, schema, endorsement_id, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await remove_polymorphic_endorsement(kind, polymorphic_ref, endorsement_id, request)
