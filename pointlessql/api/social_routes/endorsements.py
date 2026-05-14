"""Polymorphic endorsements router (Phase 77.0.F.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.endorsements import (
    apply_endorsement,
    list_endorsements,
    remove_endorsement,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/endorsements")
async def list_social_endorsements(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP endorsement list handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_endorsements(catalog, schema, request)


@router.post("/api/social/{kind}/{ref:path}/endorsements")
async def apply_social_endorsement(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP endorsement POST handler for ``kind='dp'``.

    Re-extracts ``?as_agent=`` so the speak-as-agent path survives
    the indirection.
    """
    catalog, schema = parse_dp_ref(kind, ref)
    as_agent = request.query_params.get("as_agent")
    return await apply_endorsement(
        catalog, schema, request, as_agent=as_agent
    )


@router.delete(
    "/api/social/{kind}/{ref:path}/endorsements/{endorsement_id}"
)
async def remove_social_endorsement(
    kind: str, ref: str, endorsement_id: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP endorsement DELETE handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await remove_endorsement(
        catalog, schema, endorsement_id, request
    )
