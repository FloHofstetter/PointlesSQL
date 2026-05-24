"""Polymorphic README router.

DP delegates to the Phase-71.5 versioned wiki handlers.  Non-DP
kinds use the kind-agnostic polymorphic handlers — admin-only
edits in this iteration; per-entity stewards stay a DP-only
concept.  History + diff endpoints stay DP-only for now; Phase
77.11 polish unifies them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.data_products_routes.readme import (
    get_latest_readme,
    get_readme_version,
    list_readme_history,
    readme_diff,
    upsert_readme,
)
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    get_polymorphic_readme,
    put_polymorphic_readme,
)

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/readme")
async def get_social_readme(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a latest-README GET by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await get_latest_readme(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await get_polymorphic_readme(kind, polymorphic_ref, request)


@router.get("/api/social/{kind}/{ref:path}/readme/history")
async def list_social_readme_history(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a README history list by entity kind.

    Non-DP kinds return 501.  README history + diff stays DP-only
    by design — non-DP entities use the live README only.
    """
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_readme_history(catalog, schema, request)
    # bare-http-ok: history endpoint is DP-only by design.
    raise HTTPException(
        status_code=501,
        detail=f"README history for kind={kind!r} is DP-only",
    )


@router.get("/api/social/{kind}/{ref:path}/readme/v/{version_int}")
async def get_social_readme_version(
    kind: str, ref: str, version_int: int, request: Request
) -> dict[str, Any]:
    """Dispatch a README version GET by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await get_readme_version(catalog, schema, version_int, request)
    # bare-http-ok: version-fetch endpoint is DP-only by design.
    raise HTTPException(
        status_code=501,
        detail=f"README version-fetch for kind={kind!r} is DP-only",
    )


@router.put("/api/social/{kind}/{ref:path}/readme")
async def put_social_readme(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a README upsert by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await upsert_readme(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await put_polymorphic_readme(kind, polymorphic_ref, request)


@router.get("/api/social/{kind}/{ref:path}/readme/diff")
async def get_social_readme_diff(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a README diff by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await readme_diff(catalog, schema, request)
    # bare-http-ok: diff endpoint is DP-only by design.
    raise HTTPException(
        status_code=501,
        detail=f"README diff for kind={kind!r} is DP-only",
    )
