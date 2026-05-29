"""Mesh-plane surface — the emergent graph, health, entities, traces.

Workspace-wide read endpoints + browse pages that treat the *mesh* as a
first-class plane:

* ``GET /api/mesh/graph`` — the emergent dependency graph (products as
  nodes, declared upstreams as edges).
* ``GET /api/mesh/health`` — the SLO rollup across all products.
* ``GET /api/mesh/entities`` — the polysemic-entity registry (read).
* ``GET /api/mesh/trace/{correlation_id}`` — every operation that shares
  a cross-product correlation id, as one timeline.
* ``GET /mesh`` / ``/mesh/health`` / ``/mesh/entities`` — browse pages.

All endpoints require an authenticated user; the registry is *managed*
by admins (see :mod:`pointlessql.api.admin.mesh_entities`).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
    require_user,
)
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.services import mesh as mesh_service
from pointlessql.services import slo as slo_service

router = APIRouter(tags=["mesh"])


@router.get("/api/mesh/graph")
async def api_mesh_graph(request: Request) -> dict[str, Any]:
    """Return the workspace's emergent mesh dependency graph."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return mesh_service.build_mesh_graph(factory, workspace_id=workspace_id)


@router.get("/api/mesh/health")
async def api_mesh_health(request: Request) -> dict[str, Any]:
    """Return the SLO-health rollup across every product in the mesh."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return mesh_service.mesh_health(factory, workspace_id=workspace_id)


@router.post("/api/mesh/slo-scan")
async def api_mesh_slo_scan(request: Request) -> dict[str, Any]:
    """Evaluate every product's SLOs now and log failures to the audit log."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    summary = await asyncio.to_thread(
        slo_service.scan_workspace,
        factory,
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]) if user["id"] > 0 else 0,
        actor_email=user.get("email", "system"),
    )
    await audit(
        request,
        "slo.scan_run",
        f"workspace:{workspace_id}",
        {"products_scanned": summary["products_scanned"], "violations": len(summary["violations"])},
    )
    return summary


@router.get("/api/mesh/entities")
async def api_mesh_entities(request: Request) -> dict[str, Any]:
    """List the workspace's mesh entities with binding counts."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = mesh_service.list_entities(factory, workspace_id=workspace_id)
    entities: list[dict[str, Any]] = []
    for row in rows:
        bindings = mesh_service.list_bindings(factory, mesh_entity_id=row.id)
        entities.append(
            {
                "id": row.id,
                "slug": row.slug,
                "name": row.name,
                "description": row.description,
                "binding_count": len(bindings),
                "bindings": [
                    {
                        "ref": f"{b.catalog}.{b.schema_name}.{b.table_name}.{b.column_name}",
                        "table": b.table_name,
                        "column": b.column_name,
                    }
                    for b in bindings
                ],
            }
        )
    return {"entities": entities}


@router.get("/api/mesh/trace/{correlation_id}")
async def api_mesh_trace(correlation_id: str, request: Request) -> dict[str, Any]:
    """Return every operation sharing a correlation id as a timeline.

    Args:
        correlation_id: The cross-product trace id.
        request: Incoming FastAPI request.

    Returns:
        ``{"correlation_id", "operations": [...]}`` ordered by start
        time — each op carries its run id, name, target, and timing.
    """
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    with factory() as session:
        rows = list(
            session.scalars(
                select(AgentRunOperation)
                .where(
                    AgentRunOperation.workspace_id == workspace_id,
                    AgentRunOperation.correlation_id == correlation_id,
                )
                .order_by(AgentRunOperation.started_at.asc())
            ).all()
        )
        operations = [
            {
                "id": r.id,
                "agent_run_id": r.agent_run_id,
                "ordinal": r.ordinal,
                "op_name": r.op_name,
                "target_table": r.target_table,
                "rows_affected": r.rows_affected,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error_message": r.error_message,
            }
            for r in rows
        ]
    return {"correlation_id": correlation_id, "operations": operations}


def _redirect_if_anon(request: Request, next_path: str) -> RedirectResponse | None:
    """Return a login redirect for anonymous visitors, else ``None``."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url=f"/auth/login?next={next_path}", status_code=303)
    return None


@router.get("/mesh", response_class=HTMLResponse, response_model=None)
async def mesh_graph_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the workspace mesh-graph browse page."""
    redirect = _redirect_if_anon(request, "/mesh")
    if redirect is not None:
        return redirect
    user = get_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/mesh_graph.html",
        {"active_page": "mesh", "is_admin": user["is_admin"]},
    )


@router.get("/mesh/health", response_class=HTMLResponse, response_model=None)
async def mesh_health_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the mesh-health dashboard page."""
    redirect = _redirect_if_anon(request, "/mesh/health")
    if redirect is not None:
        return redirect
    user = get_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/mesh_health.html",
        {"active_page": "mesh", "is_admin": user["is_admin"]},
    )


@router.get("/mesh/entities", response_class=HTMLResponse, response_model=None)
async def mesh_entities_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the mesh-entity registry browse page."""
    redirect = _redirect_if_anon(request, "/mesh/entities")
    if redirect is not None:
        return redirect
    user = get_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/mesh_entities.html",
        {"active_page": "mesh", "is_admin": user["is_admin"]},
    )
