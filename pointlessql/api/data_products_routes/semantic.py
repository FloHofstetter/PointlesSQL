"""Per-product semantic-model endpoints.

GET is open to any authenticated user; mutations gate on
``_require_steward_or_admin``.  Supervised agents reach the same
write path via the contract-authoring plugin tools.

* ``GET    .../{catalog}/{schema}/semantic`` — concepts + sample SQL
* ``POST   .../{catalog}/{schema}/semantic/concepts``
* ``DELETE .../{catalog}/{schema}/semantic/concepts/{concept_id}``
* ``PUT    .../{catalog}/{schema}/semantic/sample-sql``
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
from pointlessql.services import data_product_semantic as semantic_service

router = APIRouter(tags=["data-products"])


def _serialise_concept(row: Any) -> dict[str, Any]:
    """Render a :class:`DataProductSemanticConcept` row as JSON."""
    return {
        "id": row.id,
        "concept": row.concept,
        "description": row.description,
        "maps_to": row.maps_to,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/data-products/{catalog}/{schema}/semantic")
async def get_semantic(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's semantic concepts + example query."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    concepts = semantic_service.list_concepts(factory, data_product_id=dp_row.id)
    return {
        "concepts": [_serialise_concept(c) for c in concepts],
        "sample_sql": dp_row.sample_sql,
    }


@router.post("/api/data-products/{catalog}/{schema}/semantic/concepts")
async def add_concept(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Declare a business concept on this product.

    Body: ``{"concept": str, "description"?: str, "maps_to"?: str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    try:
        row = semantic_service.add_concept(
            factory,
            data_product_id=dp_row.id,
            concept=str(body.get("concept", "")),
            description=_opt_str(body.get("description")),
            maps_to=_opt_str(body.get("maps_to")),
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.semantic_concept_added",
        f"data_product:{catalog}.{schema}",
        {"concept_id": row.id, "concept": row.concept},
    )
    return _serialise_concept(row)


@router.delete("/api/data-products/{catalog}/{schema}/semantic/concepts/{concept_id}")
async def delete_concept(
    catalog: str, schema: str, concept_id: int, request: Request
) -> dict[str, Any]:
    """Remove a semantic concept from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    deleted = semantic_service.delete_concept(
        factory, data_product_id=dp_row.id, concept_id=concept_id
    )
    if deleted:
        await audit(
            request,
            "data_product.semantic_concept_removed",
            f"data_product:{catalog}.{schema}",
            {"concept_id": concept_id},
        )
    return {"deleted": deleted}


@router.put("/api/data-products/{catalog}/{schema}/semantic/sample-sql")
async def set_sample_sql(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Set or clear the product's example query.

    Body: ``{"sample_sql": str | null}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    raw = body.get("sample_sql")
    sql = raw if isinstance(raw, str) else None
    product = semantic_service.set_sample_sql(factory, data_product_id=dp_row.id, sql=sql)

    await audit(
        request,
        "data_product.sample_sql_set",
        f"data_product:{catalog}.{schema}",
        {"cleared": product.sample_sql is None},
    )
    return {"sample_sql": product.sample_sql}


def _opt_str(value: Any) -> str | None:
    """Return *value* as a trimmed string, or ``None`` when empty."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
