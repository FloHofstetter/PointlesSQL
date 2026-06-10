"""Data-Product-as-Code plan + apply + export routes."""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services import data_product_as_code as dpac_service

router = APIRouter(tags=["data-products"])


@router.get("/admin/data-product-apply", response_class=HTMLResponse)
async def admin_data_product_apply_index(request: Request) -> HTMLResponse:
    """Render the data-product-as-code admin page."""
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_data_product_apply.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


def _spec_from_body(body: dict[str, Any]) -> dpac_service.DataProductSpec:
    """Accept either ``{"spec_yaml": "..."}`` or a direct dict body."""
    raw = body.get("spec_yaml")
    payload: dict[str, Any] | str
    if isinstance(raw, str) and raw.strip():
        payload = raw
    elif isinstance(body.get("spec"), dict):
        payload = body["spec"]
    else:
        payload = body
    try:
        return dpac_service.parse_spec(payload)
    except (ValueError, yaml.YAMLError) as exc:
        raise BadRequestError(f"invalid spec: {exc}") from exc


@router.post("/api/data-products/plan")
async def plan_data_product(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Compute a Plan against the live DB without writing (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    spec = _spec_from_body(body)
    plan = dpac_service.plan_spec(factory, spec=spec, workspace_id=workspace_id)
    return {
        "plan": {
            "product_present": plan.product_present,
            "op_count": plan.op_count(),
            "is_noop": plan.is_noop(),
            "additions": [_serialise_op(o) for o in plan.additions],
            "modifications": [_serialise_op(o) for o in plan.modifications],
            "removals": [_serialise_op(o) for o in plan.removals],
        }
    }


@router.post("/api/data-products/apply")
async def apply_data_product(
    request: Request,
    dry_run: bool = False,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Apply a spec to the live DB (steward/admin) — idempotent."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    spec = _spec_from_body(body)
    if not user.get("is_admin"):
        from sqlalchemy import select

        from pointlessql.models import DataProduct

        with factory() as session:
            existing = session.scalar(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .where(DataProduct.catalog_name == spec.catalog)
                .where(DataProduct.schema_name == spec.schema)
            )
        if existing is None or existing.steward_user_id != user["id"]:
            raise AuthorizationError(
                principal=user.get("email", ""),
                privilege="steward",
                securable_type="data_product",
                full_name=f"{spec.catalog}.{spec.schema}",
            )
    plan = dpac_service.plan_spec(factory, spec=spec, workspace_id=workspace_id)
    outcome = dpac_service.apply_plan(
        factory,
        spec=spec,
        plan=plan,
        dry_run=dry_run,
        workspace_id=workspace_id,
        user_id=int(user.get("id", 0) or 0) or None,
    )
    canvas_version: int | None = None
    if not dry_run and spec.pipeline is not None:
        from sqlalchemy import select

        from pointlessql.models import DataProduct
        from pointlessql.services.data_product_as_code._canvas_pipeline import (
            to_canvas_doc,
        )
        from pointlessql.services.dp_canvas import save_graph

        with factory() as session:
            dp = session.scalar(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .where(DataProduct.catalog_name == spec.catalog)
                .where(DataProduct.schema_name == spec.schema)
            )
        if dp is not None:
            canvas_doc = to_canvas_doc(spec.pipeline)
            canvas_version = save_graph(
                factory,
                data_product_id=dp.id,
                doc=canvas_doc,
                author_user_id=int(user.get("id", 0) or 0) or None,
            )
    await audit(
        request,
        "data_product.apply",
        f"{spec.catalog}.{spec.schema}",
        {
            "dry_run": dry_run,
            "op_count": plan.op_count(),
            "applied": outcome.applied,
            "errors": outcome.errors,
            "canvas_version": canvas_version,
        },
    )
    return {
        "canvas_version": canvas_version,
        "plan": {
            "product_present": plan.product_present,
            "op_count": plan.op_count(),
            "additions": [_serialise_op(o) for o in plan.additions],
            "modifications": [_serialise_op(o) for o in plan.modifications],
            "removals": [_serialise_op(o) for o in plan.removals],
        },
        "outcome": {
            "dry_run": outcome.dry_run,
            "total": outcome.total,
            "applied": outcome.applied,
            "skipped": outcome.skipped,
            "errors": [list(e) for e in outcome.errors],
        },
    }


@router.post("/api/data-products/{catalog}/{schema}/export")
async def export_data_product(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the YAML spec for an existing product (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        spec = dpac_service.export_data_product(
            factory,
            catalog=catalog,
            schema=schema,
            workspace_id=workspace_id,
        )
    except LookupError as exc:
        raise BadRequestError(str(exc)) from exc
    return {
        "spec": spec.model_dump(),
        "spec_yaml": yaml.safe_dump(spec.model_dump(), sort_keys=False),
    }


def _serialise_op(op: dpac_service.Op) -> dict[str, Any]:
    return {
        "kind": op.kind,
        "action": op.action,
        "target": op.target,
        "before": op.before,
        "after": op.after,
    }
