"""SLO endpoints for a data product.

The full service-level-objective surface, hanging off the existing
``/api/data-products/{catalog}/{schema}`` path:

* ``GET    .../slos`` — declared objectives.
* ``POST   .../slos`` — declare/update an objective.
* ``DELETE .../slos/{slo_id}`` — remove an objective.
* ``GET    .../slo-evaluation`` — live verdicts + pass rate.

GET endpoints are open to any authenticated user; declare/delete gate on
``_require_steward_or_admin``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.proposals import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.services import slo as slo_service

router = APIRouter(tags=["data-products"])


def _serialise_slo(row: Any) -> dict[str, Any]:
    """Render a :class:`DataProductSLO` row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "table": row.table_name,
        "slo_kind": row.slo_kind,
        "target_value": row.target_value,
        "comparator": row.comparator,
        "unit": row.unit,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/data-products/{catalog}/{schema}/slos")
async def list_slos(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List the objectives declared on this product + the kind catalog."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    rows = slo_service.list_slos(factory, data_product_id=dp_row.id)
    return {
        "slos": [_serialise_slo(r) for r in rows],
        "kinds": slo_service.KIND_META,
    }


@router.post("/api/data-products/{catalog}/{schema}/slos")
async def declare_slo(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Declare or update one SLO.

    Body: ``{"slo_kind": str, "target_value"?: number, "table"?: str,
    "comparator"?: "lte"|"gte"|"eq", "unit"?: str, "enabled"?: bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    slo_kind = str(body.get("slo_kind", "")).strip()
    if not slo_kind:
        raise BadRequestError("slo_kind is required")
    target = body.get("target_value")
    creator = int(user["id"]) if user["id"] > 0 else None
    try:
        row = slo_service.declare_slo(
            factory,
            data_product_id=dp_row.id,
            slo_kind=slo_kind,
            target_value=float(target) if target is not None else None,
            table_name=body.get("table") or None,
            comparator=body.get("comparator") or None,
            unit=body.get("unit") or None,
            enabled=bool(body.get("enabled", True)),
            created_by_user_id=creator,
        )
    except (ValueError, TypeError) as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "data_product.slo_declared",
        f"data_product:{catalog}.{schema}",
        {"slo_kind": row.slo_kind, "target": row.target_value, "table": row.table_name},
    )
    return _serialise_slo(row)


@router.delete("/api/data-products/{catalog}/{schema}/slos/{slo_id}")
async def delete_slo(catalog: str, schema: str, slo_id: int, request: Request) -> dict[str, Any]:
    """Remove an SLO from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)
    deleted = slo_service.delete_slo(factory, data_product_id=dp_row.id, slo_id=slo_id)
    if deleted:
        await audit(
            request,
            "data_product.slo_removed",
            f"data_product:{catalog}.{schema}",
            {"slo_id": slo_id},
        )
    return {"deleted": deleted}


@router.get("/api/data-products/{catalog}/{schema}/slo-evaluation")
async def slo_evaluation(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return live SLO verdicts + the pass-rate roll-up for this product."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    return slo_service.evaluate_product(factory, data_product_id=dp_row.id)
