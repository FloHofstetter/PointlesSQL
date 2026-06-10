"""Entity declarations + cross-product entity-link endpoints (F3).

Steward / admin can declare and link entities on their product;
any-user can read.  Resolver lookups (``GET .../entities/resolve``)
are read-only and any-user.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services import entities as entities_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request, catalog: str, schema: str) -> None:
    """Raise 403 unless the caller is admin or the product's steward."""
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


@router.get("/api/data-products/{catalog}/{schema}/entities")
async def list_entities(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return all entities declared on the product."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return {"entities": entities_service.list_entities(factory, data_product_id=int(dp_row.id))}


@router.post("/api/data-products/{catalog}/{schema}/entities")
async def declare_entity(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Declare or update one entity on the product (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        result = entities_service.declare_entity(
            factory,
            data_product_id=int(dp_row.id),
            entity_name=str(body.get("entity_name", "")),
            source_table=str(body.get("source_table", "")),
            primary_key_columns=body.get("primary_key_columns") or [],
            description=body.get("description"),
            created_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"entity": result}


@router.delete("/api/data-products/{catalog}/{schema}/entities/{entity_id}")
async def delete_entity(
    catalog: str, schema: str, entity_id: int, request: Request
) -> dict[str, Any]:
    """Delete one entity (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    removed = entities_service.delete_entity(factory, entity_id=entity_id)
    if not removed:
        # bare-http-ok: 404 for unknown entity PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="entity not found")
    return {"deleted": True}


@router.post("/api/data-products/{catalog}/{schema}/entities/{entity_id}/links")
async def link_entities(
    catalog: str,
    schema: str,
    entity_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Declare one cross-product entity link (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    user = get_user(request)
    target = body.get("target_entity_id")
    kind = str(body.get("kind", "same_as"))
    if not isinstance(target, int):
        raise BadRequestError("target_entity_id must be an integer")
    try:
        result = entities_service.link_entities(
            factory,
            source_entity_id=entity_id,
            target_entity_id=target,
            kind=kind,
            confidence=body.get("confidence"),
            declared_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"link": result}


@router.delete("/api/data-products/{catalog}/{schema}/entities/{entity_id}/links/{link_id}")
async def unlink_entities(
    catalog: str, schema: str, entity_id: int, link_id: int, request: Request
) -> dict[str, Any]:
    """Delete one entity link (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    removed = entities_service.unlink_entities(factory, link_id=link_id)
    if not removed:
        # bare-http-ok: 404 for unknown link PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="link not found")
    return {"deleted": True}


@router.get("/api/data-products/{catalog}/{schema}/entities/{entity_id}/links")
async def list_entity_links(
    catalog: str,
    schema: str,
    entity_id: int,
    request: Request,
    direction: str = "both",
) -> dict[str, Any]:
    """Return the links incident on the entity."""
    require_user(request)
    factory = request.app.state.session_factory
    return {"links": entities_service.list_links(factory, entity_id=entity_id, direction=direction)}


@router.get("/api/data-products/{catalog}/{schema}/entities/{entity_id}/resolve")
async def resolve_entity(
    catalog: str, schema: str, entity_id: int, request: Request
) -> dict[str, Any]:
    """Return the polysemic-identity cluster for the entity."""
    require_user(request)
    factory = request.app.state.session_factory
    try:
        identity = entities_service.resolve_same_as_graph(factory, entity_id=entity_id)
    except LookupError as exc:
        # bare-http-ok: 404 for unknown entity in resolver; no domain exception.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "canonical_entity_id": identity.canonical_entity_id,
        "members": identity.members,
    }
