"""Polymorphic README router (Phase 77.0.F.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.readme import (
    get_latest_readme,
    get_readme_version,
    list_readme_history,
    readme_diff,
    upsert_readme,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/readme")
async def get_social_readme(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP latest-readme handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await get_latest_readme(catalog, schema, request)


@router.get("/api/social/{kind}/{ref:path}/readme/history")
async def list_social_readme_history(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP readme-history handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_readme_history(catalog, schema, request)


@router.get("/api/social/{kind}/{ref:path}/readme/v/{version_int}")
async def get_social_readme_version(
    kind: str, ref: str, version_int: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP readme-version handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await get_readme_version(
        catalog, schema, version_int, request
    )


@router.put("/api/social/{kind}/{ref:path}/readme")
async def put_social_readme(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP readme upsert handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await upsert_readme(catalog, schema, request)


@router.get("/api/social/{kind}/{ref:path}/readme/diff")
async def get_social_readme_diff(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP readme-diff handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await readme_diff(catalog, schema, request)
