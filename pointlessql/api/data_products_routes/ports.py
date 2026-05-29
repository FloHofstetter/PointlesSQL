"""Declared output/input port endpoints for a data product.

These hang off the existing ``/api/data-products/{catalog}/{schema}``
surface.  GET is open to any authenticated user; mutations gate on
``_require_steward_or_admin`` — the product's steward or an
install-admin may declare/remove ports, which is also the path a
supervised agent takes via the ``pql_add_data_product_*_port`` tools.

* ``GET    .../{catalog}/{schema}/output-ports``
* ``POST   .../{catalog}/{schema}/output-ports``
* ``DELETE .../{catalog}/{schema}/output-ports/{port_id}``
* ``GET    .../{catalog}/{schema}/input-ports``
* ``POST   .../{catalog}/{schema}/input-ports``
* ``DELETE .../{catalog}/{schema}/input-ports/{port_id}``
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
from pointlessql.services import data_product_ports as ports_service

router = APIRouter(tags=["data-products"])


def _serialise_output_port(row: Any) -> dict[str, Any]:
    """Render a :class:`DataProductOutputPort` row as JSON."""
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "description": row.description,
        "format": row.format,
        "location": row.location,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialise_input_port(row: Any) -> dict[str, Any]:
    """Render a :class:`DataProductInputPort` row as JSON."""
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "source_ref": row.source_ref,
        "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/data-products/{catalog}/{schema}/output-ports")
async def list_output_ports(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List the output ports declared on this product."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    rows = ports_service.list_output_ports(factory, data_product_id=dp_row.id)
    return {"output_ports": [_serialise_output_port(r) for r in rows]}


@router.post("/api/data-products/{catalog}/{schema}/output-ports")
async def create_output_port(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Declare an output port on this product.

    Body: ``{"name": str, "kind": "sql"|"file"|"event",
    "description"?: str, "format"?: str, "location"?: str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    creator_id = int(user["id"]) if user["id"] > 0 else None
    try:
        row = ports_service.create_output_port(
            factory,
            data_product_id=dp_row.id,
            name=str(body.get("name", "")),
            kind=str(body.get("kind", "")),
            description=_opt_str(body.get("description")),
            fmt=_opt_str(body.get("format")),
            location=_opt_str(body.get("location")),
            created_by_user_id=creator_id,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.output_port_declared",
        f"data_product:{catalog}.{schema}",
        {"port_id": row.id, "kind": row.kind, "name": row.name},
    )
    return _serialise_output_port(row)


@router.delete("/api/data-products/{catalog}/{schema}/output-ports/{port_id}")
async def delete_output_port(
    catalog: str, schema: str, port_id: int, request: Request
) -> dict[str, Any]:
    """Remove an output port from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    deleted = ports_service.delete_output_port(factory, data_product_id=dp_row.id, port_id=port_id)
    if deleted:
        await audit(
            request,
            "data_product.output_port_removed",
            f"data_product:{catalog}.{schema}",
            {"port_id": port_id},
        )
    return {"deleted": deleted}


@router.get("/api/data-products/{catalog}/{schema}/input-ports")
async def list_input_ports(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """List the input ports declared on this product."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    rows = ports_service.list_input_ports(factory, data_product_id=dp_row.id)
    return {"input_ports": [_serialise_input_port(r) for r in rows]}


@router.post("/api/data-products/{catalog}/{schema}/input-ports")
async def create_input_port(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Declare an upstream input port on this product.

    Body: ``{"name": str, "kind": "operational_system"|
    "upstream_product"|"external", "source_ref"?: str,
    "description"?: str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    creator_id = int(user["id"]) if user["id"] > 0 else None
    try:
        row = ports_service.create_input_port(
            factory,
            data_product_id=dp_row.id,
            name=str(body.get("name", "")),
            kind=str(body.get("kind", "")),
            source_ref=_opt_str(body.get("source_ref")),
            description=_opt_str(body.get("description")),
            created_by_user_id=creator_id,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await audit(
        request,
        "data_product.input_port_declared",
        f"data_product:{catalog}.{schema}",
        {"port_id": row.id, "kind": row.kind, "name": row.name},
    )
    return _serialise_input_port(row)


@router.delete("/api/data-products/{catalog}/{schema}/input-ports/{port_id}")
async def delete_input_port(
    catalog: str, schema: str, port_id: int, request: Request
) -> dict[str, Any]:
    """Remove an input port from this product."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    deleted = ports_service.delete_input_port(factory, data_product_id=dp_row.id, port_id=port_id)
    if deleted:
        await audit(
            request,
            "data_product.input_port_removed",
            f"data_product:{catalog}.{schema}",
            {"port_id": port_id},
        )
    return {"deleted": deleted}


def _opt_str(value: Any) -> str | None:
    """Return *value* as a trimmed string, or ``None`` when empty."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
