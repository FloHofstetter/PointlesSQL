"""Admin CRUD for the polysemic mesh-entity registry.

The shared business-entity vocabulary is curated like the glossary:
tenant-admin-gated JSON endpoints plus one HTML cockpit page.  Binding an
entity to a *product's* column happens on the product's Interop tab
(steward/admin of that product); here admins only manage the entity
names themselves.

* ``GET    /admin/mesh-entities`` — HTML list + create form.
* ``GET    /api/admin/mesh-entities`` — list entities in the workspace.
* ``POST   /api/admin/mesh-entities`` — create an entity.
* ``DELETE /api/admin/mesh-entities/{id}`` — delete (CASCADEs bindings).

Every mutation logs to :class:`AuditLog` with the ``mesh_entity.*``
action prefix.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import ValidationError
from pointlessql.models import MeshEntity
from pointlessql.services import mesh as mesh_service

router = APIRouter(tags=["admin-mesh-entities"])


def _serialize_entity(row: MeshEntity) -> dict[str, Any]:
    """Project a :class:`MeshEntity` ORM row to a JSON-safe dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/admin/mesh-entities")
async def api_admin_list_entities(request: Request) -> dict[str, Any]:
    """List the active workspace's mesh entities with binding counts."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = mesh_service.list_entities(factory, workspace_id=workspace_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = _serialize_entity(row)
        payload["binding_count"] = len(mesh_service.list_bindings(factory, mesh_entity_id=row.id))
        out.append(payload)
    return {"entities": out}


@router.post("/api/admin/mesh-entities")
async def api_admin_create_entity(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a mesh entity.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name": str, "slug"?: str, "description"?: str}``.

    Returns:
        The serialized entity row.

    Raises:
        ValidationError: On an empty name or invalid slug.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name must be a non-empty string")
    slug = body.get("slug")
    description = body.get("description")
    user = get_user(request)
    creator = int(user["id"]) if user["id"] > 0 else None
    try:
        row = mesh_service.create_entity(
            factory,
            workspace_id=workspace_id,
            name=name,
            slug=slug if isinstance(slug, str) and slug.strip() else None,
            description=description if isinstance(description, str) else "",
            created_by_user_id=creator,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "mesh_entity.created",
        f"mesh_entity:{row.slug}",
        {"id": row.id, "slug": row.slug, "name": row.name},
    )
    return _serialize_entity(row)


@router.delete("/api/admin/mesh-entities/{entity_id}")
async def api_admin_delete_entity(request: Request, entity_id: int) -> dict[str, Any]:
    """Delete a mesh entity (and, via CASCADE, its bindings)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    deleted = mesh_service.delete_entity(factory, workspace_id=workspace_id, entity_id=entity_id)
    if deleted:
        await audit(
            request,
            "mesh_entity.deleted",
            f"mesh_entity:{entity_id}",
            {"id": entity_id},
        )
    return {"deleted": deleted}


@router.get("/admin/mesh-entities", response_class=HTMLResponse)
async def admin_mesh_entities_page(request: Request):
    """Render the admin mesh-entity cockpit (list + create)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    entities = mesh_service.list_entities(factory, workspace_id=workspace_id)
    binding_counts: dict[int, int] = {
        row.id: len(mesh_service.list_bindings(factory, mesh_entity_id=row.id)) for row in entities
    }
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_mesh_entities.html",
        {
            "active_page": "admin",
            "entities": entities,
            "binding_counts": binding_counts,
        },
    )
