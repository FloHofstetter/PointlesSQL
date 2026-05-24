"""``/api/data-products/{catalog}/{schema}/passport``.

Two endpoints:

* ``GET /passport`` — latest passport row + the versions list.
* ``POST /passport/refresh`` — admin / steward manual trigger.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import desc, select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models.catalog._data_product_passport import DataProductPassport
from pointlessql.services.data_products import refresh_passport_for_dp

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(user: Any, row: Any) -> None:
    """Raise unless the caller is the DP's steward or an install-admin."""
    is_steward = (
        row.steward_user_id is not None and row.steward_user_id == user["id"]
    )
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="passport-refresh",
            securable_type="data_product",
            full_name=f"{row.catalog_name}.{row.schema_name}",
        )


def _serialise_passport(row: DataProductPassport) -> dict[str, Any]:
    """Render one passport row as JSON.

    Args:
        row: The passport ORM row.

    Returns:
        JSON-friendly dict.
    """
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "version_int": row.version_int,
        "body_md": row.body_md,
        "source_tables": json.loads(row.source_tables_json or "[]"),
        "downstream_tables": json.loads(row.downstream_tables_json or "[]"),
        "column_count": row.column_count,
        "edge_count": row.edge_count,
        "refreshed_at": row.refreshed_at.isoformat(),
        "refresh_trigger": row.refresh_trigger,
    }


@router.get("/api/data-products/{catalog}/{schema}/passport")
async def get_latest_passport(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the latest passport for the product + the versions list.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"latest": {...} | None, "versions": [{id, version_int,
        refreshed_at, trigger}, ...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        latest = session.execute(
            select(DataProductPassport)
            .where(
                DataProductPassport.workspace_id == workspace_id,
                DataProductPassport.data_product_id == row.id,
            )
            .order_by(desc(DataProductPassport.version_int))
            .limit(1)
        ).scalar_one_or_none()
        versions = (
            session.execute(
                select(DataProductPassport)
                .where(
                    DataProductPassport.workspace_id == workspace_id,
                    DataProductPassport.data_product_id == row.id,
                )
                .order_by(desc(DataProductPassport.version_int))
            )
            .scalars()
            .all()
        )
        latest_payload = _serialise_passport(latest) if latest is not None else None
        versions_payload = [
            {
                "id": v.id,
                "version_int": v.version_int,
                "refreshed_at": v.refreshed_at.isoformat(),
                "refresh_trigger": v.refresh_trigger,
            }
            for v in versions
        ]
    return {"latest": latest_payload, "versions": versions_payload}


@router.post("/api/data-products/{catalog}/{schema}/passport/refresh")
async def post_refresh_passport(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Trigger a manual passport refresh.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"version_int": int}`` for the new passport row.

    Raises:
        HTTPException: 404 when the DP doesn't exist.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, row)

    version_int = refresh_passport_for_dp(
        factory,
        workspace_id=workspace_id,
        data_product_id=row.id,
        trigger="manual",
    )
    if version_int == 0:
        raise ResourceNotFoundError("data product not found.")
    return {"version_int": version_int}
