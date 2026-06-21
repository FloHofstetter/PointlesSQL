"""Admin surface for predictive-optimization maintenance policies.

A control console over the autonomous Delta maintenance plane: set a
per-catalog / schema / table policy declaring which operations
(OPTIMIZE, VACUUM, ANALYZE) should run, and resolve the effective policy
for any table (most-specific scope wins).  The maintenance execution
itself stays on the PQL / deltalake path; this surface is the control +
visibility layer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.models import OPTIMIZATION_SCOPE_TYPES
from pointlessql.services import predictive_optimization

router = APIRouter(tags=["admin-optimization"])


@router.get("/admin/optimization", response_class=HTMLResponse)
async def admin_optimization_index(request: Request) -> HTMLResponse:
    """Render the predictive-optimization policy console.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The rendered ``pages/admin_optimization.html`` response.
    """
    require_admin(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_optimization.html",
        {
            "active_page": "admin",
            "scope_types": list(OPTIMIZATION_SCOPE_TYPES),
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/optimization")
async def list_optimization_policies(request: Request) -> dict[str, Any]:
    """List the workspace's maintenance policies."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {"policies": predictive_optimization.list_policies(factory, workspace_id=workspace_id)}


@router.post("/api/admin/optimization")
async def set_optimization_policy(
    request: Request, body: dict[str, Any] = Body(default_factory=dict[str, Any])
) -> dict[str, Any]:
    """Create or update a maintenance policy for a scope.

    Args:
        request: Incoming FastAPI request.
        body: JSON with ``scope_type`` / ``scope_value`` and optional
            ``enabled`` / ``optimize`` / ``vacuum`` / ``analyze`` /
            ``vacuum_retention_hours``.  A malformed scope propagates the
            service's :class:`ValidationError` (HTTP 400).

    Returns:
        ``{"policy": {...}}`` with the persisted policy.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    created_by = get_user(request)["email"] or None
    retention = body.get("vacuum_retention_hours")
    policy = predictive_optimization.set_policy(
        factory,
        workspace_id=workspace_id,
        scope_type=str(body.get("scope_type") or ""),
        scope_value=str(body.get("scope_value") or ""),
        enabled=bool(body.get("enabled", True)),
        optimize=bool(body.get("optimize", True)),
        vacuum=bool(body.get("vacuum", True)),
        analyze=bool(body.get("analyze", True)),
        vacuum_retention_hours=int(retention) if isinstance(retention, int) else None,
        created_by=created_by,
    )
    return {"policy": policy}


@router.delete("/api/admin/optimization/{policy_id}")
async def delete_optimization_policy(request: Request, policy_id: int) -> dict[str, Any]:
    """Delete a maintenance policy."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return {
        "deleted": predictive_optimization.delete_policy(
            factory, policy_id=policy_id, workspace_id=workspace_id
        )
    }


@router.get("/api/admin/optimization/effective")
async def effective_optimization_policy(
    request: Request, table: str = Query(..., description="catalog.schema.table")
) -> dict[str, Any]:
    """Resolve the effective maintenance policy for a table.

    Args:
        request: Incoming FastAPI request.
        table: Three-part ``catalog.schema.table`` to resolve.

    Returns:
        The resolution from
        :func:`predictive_optimization.effective_policy`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return predictive_optimization.effective_policy(
        factory, workspace_id=workspace_id, full_name=table.strip()
    )
