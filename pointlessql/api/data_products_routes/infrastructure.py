"""Infrastructure declaration endpoints (B8).

GET / PUT a product's storage-class / compute-runtime / access-method
declaration.  Steward / admin gate on the write side; any-user read.
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
from pointlessql.services import infrastructure as infrastructure_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request, catalog: str, schema: str) -> None:
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    if user.get("is_admin"):
        return
    if dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="steward",
        securable_type="data_product",
        full_name=f"{catalog}.{schema}",
    )


@router.get("/api/data-products/{catalog}/{schema}/infrastructure")
async def get_infrastructure(
    catalog: str, schema: str, request: Request
) -> dict[str, Any]:
    """Return the product's infrastructure declaration."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return {
        "infrastructure": infrastructure_service.get_infrastructure(
            factory, data_product_id=int(dp_row.id)
        )
    }


@router.put("/api/data-products/{catalog}/{schema}/infrastructure")
async def set_infrastructure(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Upsert the product's infrastructure declaration (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        result = infrastructure_service.set_infrastructure(
            factory,
            data_product_id=int(dp_row.id),
            fields=body,
            updated_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"infrastructure": result}
