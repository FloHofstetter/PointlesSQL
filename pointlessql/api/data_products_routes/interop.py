"""Interoperability endpoints for a data product.

The product-scoped half of the mesh plane, hanging off the existing
``/api/data-products/{catalog}/{schema}`` surface:

* ``GET    .../mesh-graph`` — the product's neighbourhood in the mesh.
* ``GET    .../entities`` — entities bound to this product's columns +
  the available registry.
* ``POST   .../entities`` — bind one column to a mesh entity.
* ``DELETE .../entities/{binding_id}`` — remove a binding.
* ``GET    .../joinable?other=cat.schema`` — shared-entity join keys.
* ``POST   .../point-in-time-read`` — resolve a consistent as-of
  snapshot manifest across this product (+ optional extra products).
* ``GET    .../interop`` — the aggregate the Interop tab renders.

GET endpoints are open to any authenticated user; binds + the
point-in-time read gate on ``_require_steward_or_admin``.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.proposals import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_uc_client,
    get_user,
    require_user,
)
from pointlessql.config import Settings
from pointlessql.exceptions import BadRequestError
from pointlessql.services import mesh as mesh_service

router = APIRouter(tags=["data-products"])


def _serialise_binding(row: Any) -> dict[str, Any]:
    """Render a mesh-entity binding row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "mesh_entity_id": row.mesh_entity_id,
        "table": row.table_name,
        "column": row.column_name,
        "ref": f"{row.catalog}.{row.schema_name}.{row.table_name}.{row.column_name}",
    }


def _resolve_other_product(factory: Any, workspace_id: int, ref: str) -> int | None:
    """Resolve a ``catalog.schema`` ref to a product id in the workspace."""
    from sqlalchemy import select

    from pointlessql.models import DataProduct

    if "." not in ref:
        return None
    catalog, _, schema = ref.partition(".")
    with factory() as session:
        return session.scalar(
            select(DataProduct.id).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog.strip(),
                DataProduct.schema_name == schema.strip(),
            )
        )


@router.get("/api/data-products/{catalog}/{schema}/mesh-graph")
async def get_mesh_graph(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's local neighbourhood in the mesh graph."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    hops = max(1, int(request.query_params.get("hops", "1") or "1"))
    return mesh_service.build_local_mesh(
        factory, workspace_id=workspace_id, data_product_id=dp_row.id, hops=hops
    )


@router.get("/api/data-products/{catalog}/{schema}/entities")
async def list_entity_bindings(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the entities bound to this product + the available registry."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    bindings = mesh_service.list_bindings(factory, data_product_id=dp_row.id)
    available = mesh_service.list_entities(factory, workspace_id=workspace_id)
    is_admin = bool(user.get("is_admin"))
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    return {
        "can_manage": is_admin or is_steward,
        "bindings": [_serialise_binding(b) for b in bindings],
        "available_entities": [{"id": e.id, "slug": e.slug, "name": e.name} for e in available],
    }


@router.post("/api/data-products/{catalog}/{schema}/entities")
async def bind_entity_column(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Bind one of this product's columns to a mesh entity.

    Body: ``{"entity_slug": str, "table": str, "column": str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    entity_slug = str(body.get("entity_slug", "")).strip()
    table = str(body.get("table", "")).strip()
    column = str(body.get("column", "")).strip()
    if not entity_slug or not table or not column:
        raise BadRequestError("entity_slug, table and column are required")

    entities = {
        e.slug: e.id for e in mesh_service.list_entities(factory, workspace_id=workspace_id)
    }
    entity_id = entities.get(entity_slug)
    if entity_id is None:
        raise BadRequestError(f"mesh entity {entity_slug!r} not found in this workspace")

    creator = int(user["id"]) if user["id"] > 0 else None
    try:
        row = mesh_service.add_binding(
            factory,
            mesh_entity_id=entity_id,
            data_product_id=dp_row.id,
            catalog=catalog,
            schema=schema,
            table=table,
            column=column,
            created_by_user_id=creator,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "mesh_entity.column_bound",
        f"data_product:{catalog}.{schema}",
        {"entity_slug": entity_slug, "table": table, "column": column},
    )
    return _serialise_binding(row)


@router.delete("/api/data-products/{catalog}/{schema}/entities/{binding_id}")
async def unbind_entity_column(
    catalog: str, schema: str, binding_id: int, request: Request
) -> dict[str, Any]:
    """Remove a mesh-entity binding from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)
    deleted = mesh_service.delete_binding(factory, binding_id=binding_id)
    if deleted:
        await audit(
            request,
            "mesh_entity.column_unbound",
            f"data_product:{catalog}.{schema}",
            {"binding_id": binding_id},
        )
    return {"deleted": deleted}


@router.get("/api/data-products/{catalog}/{schema}/joinable")
async def joinable(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return shared-entity join keys between this product and ``other``.

    Query param ``other`` is a ``catalog.schema`` ref.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    other_ref = request.query_params.get("other", "").strip()
    if not other_ref:
        raise BadRequestError("query param 'other' (catalog.schema) is required")
    other_id = _resolve_other_product(factory, workspace_id, other_ref)
    if other_id is None:
        raise BadRequestError(f"product {other_ref!r} not found in this workspace")
    suggestions = mesh_service.joinable_columns(
        factory, left_product_id=dp_row.id, right_product_id=other_id
    )
    return {"other": other_ref, "suggestions": suggestions}


@router.get("/api/data-products/{catalog}/{schema}/point-in-time-read")
async def point_in_time_read_get(
    catalog: str,
    schema: str,
    request: Request,
    as_of: str,
) -> dict[str, Any]:
    """GET-equivalent of the POST point-in-time endpoint.

    Browser + plugin callers prefer a query-string interface so the
    URL is shareable.  The path resolves the same manifest as the
    POST sibling for the target product alone.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        as_of: ISO-8601 timestamp.  ``Z`` is normalised to ``+00:00``;
            naive values default to UTC.

    Returns:
        Same shape as :func:`point_in_time_read`.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    raw = as_of.strip()
    if not raw:
        raise BadRequestError("'as_of' (ISO-8601 timestamp) is required")
    try:
        when = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequestError(f"invalid 'as_of' timestamp: {raw!r}") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.UTC)

    uc = get_uc_client(request)
    try:
        return await mesh_service.resolve_as_of(
            factory,
            uc,
            workspace_id=workspace_id,
            product_ids=[dp_row.id],
            when=when,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc


@router.post("/api/data-products/{catalog}/{schema}/point-in-time-read")
async def point_in_time_read(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Resolve a consistent as-of snapshot manifest across products.

    Body: ``{"when": iso8601, "products"?: ["cat.schema", ...]}``.  The
    target product is always included; extra products are added by ref.
    Returns the resolved Delta version + row count per declared table —
    the manifest a consumer uses to pull a reproducible cross-product
    snapshot.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    when_raw = str(body.get("when", "")).strip()
    if not when_raw:
        raise BadRequestError("'when' (ISO-8601 timestamp) is required")
    try:
        when = datetime.datetime.fromisoformat(when_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequestError(f"invalid 'when' timestamp: {when_raw!r}") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.UTC)

    product_ids = [dp_row.id]
    for ref in body.get("products", []) or []:
        other_id = _resolve_other_product(factory, workspace_id, str(ref))
        if other_id is not None and other_id not in product_ids:
            product_ids.append(other_id)

    uc = get_uc_client(request)
    try:
        manifest = await mesh_service.resolve_as_of(
            factory, uc, workspace_id=workspace_id, product_ids=product_ids, when=when
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return manifest


@router.get("/api/data-products/{catalog}/{schema}/interop")
async def interop_aggregate(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the aggregate the Interop tab renders.

    Local mesh neighbourhood + entity bindings + the available entity
    registry + the bitemporal convention + a manage flag.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    is_admin = bool(user.get("is_admin"))
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    bindings = mesh_service.list_bindings(factory, data_product_id=dp_row.id)
    available = mesh_service.list_entities(factory, workspace_id=workspace_id)
    settings: Settings = request.app.state.settings
    return {
        "can_manage": is_admin or is_steward,
        "neighbourhood": mesh_service.build_local_mesh(
            factory, workspace_id=workspace_id, data_product_id=dp_row.id, hops=1
        ),
        "bindings": [_serialise_binding(b) for b in bindings],
        "available_entities": [{"id": e.id, "slug": e.slug, "name": e.name} for e in available],
        "bitemporal": {
            "inject_processing_time": settings.bitemporal.inject_processing_time,
            "processing_time_column": settings.bitemporal.processing_time_column,
            "event_time_column": settings.bitemporal.event_time_column,
        },
    }
