"""Admin endpoints for Cedar policy-module CRUD + dry-run + decisions.

Admin-gated surface.  Every mutation routes through the policy-as-code
service module so the cache invalidation + version bump happens in
exactly one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.services import policy_as_code as policy_service

router = APIRouter(tags=["admin-policy-modules"])


@router.get("/admin/policy-modules", response_class=HTMLResponse)
async def admin_policy_modules_index(request: Request) -> HTMLResponse:
    """Render the Cedar policy-modules admin page."""
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_policy_modules.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/policy-modules")
async def list_policy_modules(
    request: Request, include_disabled: bool = True
) -> dict[str, Any]:
    """Return every module in the current workspace."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "modules": policy_service.list_modules(
            factory,
            workspace_id=workspace_id,
            include_disabled=include_disabled,
        )
    }


@router.post("/api/admin/policy-modules")
async def create_policy_module(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Create a Cedar policy module (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    try:
        module = policy_service.create_module(
            factory,
            workspace_id=workspace_id,
            name=str(body.get("name", "")),
            cedar_source=str(body.get("cedar_source", "")),
            enabled=bool(body.get("enabled", True)),
            created_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        "policy_module.created",
        f"policy_module:{module['id']}",
        {"name": module["name"], "version": module["version"]},
    )
    return {"module": module}


@router.put("/api/admin/policy-modules/{module_id}")
async def update_policy_module(
    module_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Update name / cedar_source / enabled flag (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    try:
        module = policy_service.update_module(
            factory,
            module_id=module_id,
            cedar_source=body.get("cedar_source"),
            name=body.get("name"),
            enabled=body.get("enabled"),
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    if module is None:
        # bare-http-ok: 404 for unknown module PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="policy module not found")
    await audit(
        request,
        "policy_module.updated",
        f"policy_module:{module_id}",
        {"version": module["version"], "enabled": module["enabled"]},
    )
    return {"module": module}


@router.delete("/api/admin/policy-modules/{module_id}")
async def delete_policy_module(module_id: int, request: Request) -> dict[str, Any]:
    """Delete one module (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    removed = policy_service.delete_module(factory, module_id=module_id)
    if not removed:
        # bare-http-ok: 404 for unknown module PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="policy module not found")
    await audit(
        request,
        "policy_module.deleted",
        f"policy_module:{module_id}",
        None,
    )
    return {"deleted": True}


@router.post("/api/admin/policy-modules/{module_id}/test")
async def test_policy_module(
    module_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Dry-run a module against a principal / action / resource (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    module = policy_service.get_module(factory, module_id=module_id)
    if module is None:
        # bare-http-ok: 404 for unknown module PK; no domain exception needed.
        raise HTTPException(status_code=404, detail="policy module not found")
    principal = str(body.get("principal", 'User::"test"'))
    action = str(body.get("action", 'Action::"read"'))
    resource = str(body.get("resource", 'DataProduct::"main.silver"'))
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    from pointlessql.models import PolicyModule
    with factory() as session:
        row = session.get(PolicyModule, module_id)
        if row is None:
            # bare-http-ok: race between get_module and refetch.
            raise HTTPException(status_code=404, detail="policy module not found")
        decision = policy_service.cedar_evaluate(
            [row],
            principal=principal,
            action=action,
            resource=resource,
            context=context,
        )
    return {
        "decision": {
            "effect": decision.effect,
            "empty": decision.empty,
            "latency_ms": decision.latency_ms,
            "diagnostics": decision.diagnostics,
            "error_class": decision.error_class,
        }
    }


@router.get("/api/admin/policy-modules/{module_id}/decisions")
async def list_policy_decisions(
    module_id: int, request: Request, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    """Return the decision log for one module (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    return {
        "decisions": policy_service.list_decisions(
            factory, module_id=module_id, limit=limit, offset=offset
        )
    }


@router.put("/api/data-products/{catalog}/{schema}/policy-modules")
async def link_policy_modules_to_product(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Link / unlink policy modules to a data product (steward/admin)."""
    from pointlessql.api.data_products_routes._shared import load_one

    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    if not user.get("is_admin") and (
        dp_row.steward_user_id is None or dp_row.steward_user_id != user["id"]
    ):
        # bare-http-ok: steward/admin guard mirrors the entity-routes pattern.
        raise HTTPException(status_code=403, detail="steward or admin required")
    raw_ids = body.get("module_ids", []) or []
    if not isinstance(raw_ids, list):
        raise BadRequestError("module_ids must be a list of integers")
    module_ids = [int(m) for m in raw_ids if isinstance(m, int)]
    linked = policy_service.link_modules_to_product(
        factory,
        data_product_id=int(dp_row.id),
        module_ids=module_ids,
        updated_by_user_id=int(user.get("id", 0) or 0) or None,
    )
    await audit(
        request,
        "policy_module.linked_to_product",
        f"{catalog}.{schema}",
        {"module_ids": linked},
    )
    return {"linked_module_ids": linked}
