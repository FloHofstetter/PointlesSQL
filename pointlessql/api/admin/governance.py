"""Admin governance — the workspace-default policy + on-demand scan.

Tenant-admin-gated surface for the mesh-level half of governance:

* ``GET  /api/admin/governance/policy`` — the workspace default policy.
* ``PUT  /api/admin/governance/policy`` — set the workspace defaults
  every product inherits unless it overrides them.
* ``POST /api/admin/governance/scan`` — run the policy-compliance scan
  now (the same checks the scheduled job runs), logging findings to the
  audit log.
* ``GET  /admin/governance`` — the HTML cockpit page.

Every mutation logs to :class:`AuditLog` with the ``governance.*``
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
from pointlessql.config import Settings
from pointlessql.services import governance as governance_service
from pointlessql.services._executor import run_sync

router = APIRouter(tags=["admin-governance"])


@router.get("/api/admin/governance/policy")
async def api_admin_get_policy(request: Request) -> dict[str, Any]:
    """Return the workspace default policy."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "workspace_default": governance_service.get_workspace_policy(
            factory, workspace_id=workspace_id
        )
    }


@router.put("/api/admin/governance/policy")
async def api_admin_set_policy(
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Set the workspace default policy.

    Body keys (all optional): ``retention_days``, ``encryption_class``,
    ``residency_region``, ``consent_required``, ``consent_basis``.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    fields = {k: body[k] for k in governance_service.POLICY_FIELDS if k in body}
    updater = int(user["id"]) if user["id"] > 0 else None
    governance_service.set_workspace_policy(
        factory, workspace_id=workspace_id, fields=fields, updated_by_user_id=updater
    )
    await audit(
        request,
        "governance.workspace_policy_set",
        f"workspace:{workspace_id}",
        {"fields": list(fields.keys())},
    )
    return {
        "workspace_default": governance_service.get_workspace_policy(
            factory, workspace_id=workspace_id
        )
    }


@router.post("/api/admin/governance/scan")
async def api_admin_run_scan(request: Request) -> dict[str, Any]:
    """Run the policy-compliance scan now and return a summary."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    settings: Settings = request.app.state.settings
    summary = await run_sync(
        governance_service.scan_workspace,
        factory,
        settings,
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]) if user["id"] > 0 else 0,
        actor_email=user.get("email", "system"),
    )
    await audit(
        request,
        "governance.scan_run",
        f"workspace:{workspace_id}",
        {"products_scanned": summary["products_scanned"], "violations": len(summary["violations"])},
    )
    return summary


@router.get("/admin/governance", response_class=HTMLResponse)
async def admin_governance_page(request: Request):
    """Render the admin governance cockpit (workspace default + scan)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_governance.html",
        {
            "active_page": "admin",
            "workspace_default": governance_service.get_workspace_policy(
                factory, workspace_id=workspace_id
            ),
        },
    )
