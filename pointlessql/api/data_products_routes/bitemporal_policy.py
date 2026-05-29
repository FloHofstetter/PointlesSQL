"""Per-product bitemporal-policy override (F1/F5).

Wraps :func:`pointlessql.services.bitemporal.set_product_policy` for
steward / admin writes; reads go through the discovery envelope's
``bitemporal`` block already.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services.bitemporal import set_product_policy

router = APIRouter(tags=["data-products"])


@router.put("/api/data-products/{catalog}/{schema}/bitemporal-policy")
async def put_bitemporal_policy(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Upsert the per-product bitemporal override (steward/admin)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    is_admin = bool(user.get("is_admin"))
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    if not (is_admin or is_steward):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="steward",
            securable_type="data_product",
            full_name=f"{catalog}.{schema}",
        )
    try:
        row = set_product_policy(
            factory,
            data_product_id=int(dp_row.id),
            fields=body,
            updated_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {
        "enforcement": row.enforcement,
        "processing_time_column": row.processing_time_column,
        "event_time_column": row.event_time_column,
        "require_event_time": row.require_event_time,
    }
