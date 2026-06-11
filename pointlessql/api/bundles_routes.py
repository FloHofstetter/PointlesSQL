"""Asset-bundle plan / apply / export routes plus the admin page.

All endpoints are admin-only: a bundle can rewire jobs that run as
other principals and replace dashboard widgets wholesale, so the
surface mirrors the rest of the admin console rather than the
steward-scoped data-product apply flow.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.services import asset_bundles as bundles_service

router = APIRouter(tags=["bundles"])


@router.get("/admin/bundles", response_class=HTMLResponse)
async def admin_bundles_index(request: Request) -> HTMLResponse:
    """Render the asset-bundle admin page."""
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_bundles.html",
        {
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


def _spec_from_body(body: dict[str, Any]) -> bundles_service.BundleSpec:
    """Accept either ``{"bundle_yaml": "..."}`` or a direct dict body.

    Args:
        body: Decoded JSON request body.

    Returns:
        The validated bundle spec.

    Raises:
        BadRequestError: When neither shape parses into a valid spec.
    """
    raw = body.get("bundle_yaml")
    payload: dict[str, Any] | str = raw if isinstance(raw, str) and raw.strip() else body
    try:
        return bundles_service.parse_bundle(payload)
    except ValueError as exc:
        raise BadRequestError(f"invalid bundle: {exc}") from exc


def _serialise_plan(plan: bundles_service.BundlePlan) -> dict[str, Any]:
    """Flatten a :class:`BundlePlan` into the JSON response shape."""
    return {
        "is_noop": plan.is_noop(),
        "entries": [
            {
                "resource_type": entry.resource_type,
                "identity": entry.identity,
                "action": entry.action,
                "changes": entry.changes,
            }
            for entry in plan.entries
        ],
        "orphans": [
            {"resource_type": orphan.resource_type, "identity": orphan.identity}
            for orphan in plan.orphans
        ],
    }


@router.post("/api/bundles/plan")
async def plan_bundle_route(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Compute the bundle plan against the live DB without writing.

    Rejects with 400 when the spec is invalid or a declared resource
    cannot be diffed (bad pipeline SQL, ambiguous widget matching).
    """
    require_admin(request)
    spec = _spec_from_body(body)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        plan = bundles_service.plan_bundle(factory, spec=spec, workspace_id=workspace_id)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"plan": _serialise_plan(plan)}


@router.post("/api/bundles/apply")
async def apply_bundle_route(
    request: Request,
    dry_run: bool = False,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Apply a bundle spec to the live DB — idempotent per resource."""
    require_admin(request)
    spec = _spec_from_body(body)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    outcome = bundles_service.apply_bundle(
        factory,
        spec=spec,
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]),
        actor_email=str(user["email"]),
        dry_run=dry_run,
    )
    results = [
        {
            "resource_type": result.resource_type,
            "identity": result.identity,
            "action": result.action,
            "error": result.error,
        }
        for result in outcome.results
    ]
    await audit(
        request,
        "bundle.apply",
        f"bundle:{spec.bundle.name}",
        {
            "dry_run": dry_run,
            "resources": len(results),
            "errors": outcome.error_count(),
        },
    )
    return {
        "outcome": {
            "dry_run": outcome.dry_run,
            "error_count": outcome.error_count(),
            "results": results,
        }
    }


@router.post("/api/bundles/export")
async def export_bundle_route(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Export live resources as a bundle YAML document.

    Each of ``jobs`` / ``pipelines`` / ``dashboards`` selects by
    name / slug; omitted (or ``null``) exports all of that resource
    type, an empty list exports none.  Rejects with 400 when a
    selector is not a list of strings or a selected resource cannot
    be represented as a spec.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    selectors: dict[str, list[str] | None] = {}
    for field in ("jobs", "pipelines", "dashboards"):
        raw = body.get(field)
        if raw is None:
            selectors[field] = None
            continue
        if not isinstance(raw, list):
            raise BadRequestError(f"{field} must be a list of strings when provided")
        items = cast("list[object]", raw)
        if not all(isinstance(item, str) for item in items):
            raise BadRequestError(f"{field} must be a list of strings when provided")
        selectors[field] = [str(item) for item in items]
    try:
        spec = bundles_service.export_bundle(
            factory,
            workspace_id=workspace_id,
            jobs=selectors["jobs"],
            pipelines=selectors["pipelines"],
            dashboards=selectors["dashboards"],
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return {"yaml": bundles_service.bundle_to_yaml(spec)}
