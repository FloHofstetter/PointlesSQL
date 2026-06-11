"""Data-quality monitoring routes — monitor CRUD, scans, and the page.

JSON surface under ``/api/quality/*`` plus the ``/quality`` HTML
cockpit.  Reading (list / detail / anomalies / page) is open to any
signed-in user; creating, patching, deleting, and manually running
monitors is admin-only — monitors fan scheduler jobs out over the
lakehouse, which is an operator concern.

The manual scan goes through the scheduler's ``execute_run`` against
the monitor's hidden backing job, so interactive runs share the
telemetry, principal, and run-history path with cron ticks.  The
module keeps its own one-kind registry so the route works regardless
of when the global scheduler registry learns the
``"quality_monitor"`` kind.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.services import quality_monitoring as quality_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services._executor import run_sync

router = APIRouter(tags=["quality"])

# One-kind registry for the manual "scan now" path.  Self-contained
# so the route never depends on the global scheduler registry's
# wiring order; the scheduler loop registers the same executor for
# cron ticks through its default registry.
_QUALITY_REGISTRY = scheduler_service.KindRegistry()
_QUALITY_REGISTRY.register("quality_monitor", quality_service.quality_monitor_executor)


@router.get("/api/quality/monitors")
async def api_list_monitors(request: Request) -> dict[str, Any]:
    """List the active workspace's quality monitors."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    monitors = await run_sync(quality_service.list_monitors, factory, workspace_id=workspace_id)
    return {"monitors": monitors}


@router.post("/api/quality/monitors", dependencies=[Depends(require_admin)])
async def api_create_monitor(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a quality monitor (admin only).

    Args:
        request: Incoming FastAPI request.
        body: ``{"target", "cron_expr", "is_active"?}``.

    Returns:
        The serialised monitor.
    """
    user = get_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    monitor = await run_sync(
        quality_service.create_monitor,
        factory,
        workspace_id=workspace_id,
        target=str(body.get("target", "")),
        cron_expr=str(body.get("cron_expr", "")),
        created_by_user_id=int(user["id"]),
        is_active=bool(body.get("is_active", True)),
    )
    await audit(
        request,
        "quality_monitor.created",
        f"quality_monitor:{monitor['id']}",
        {"target": monitor["target"]},
    )
    return monitor


def _ensure_monitor(request: Request, monitor_id: int) -> dict[str, Any]:
    """Return the workspace's monitor or raise a 404.

    Args:
        request: Incoming FastAPI request.
        monitor_id: Monitor id from the URL.

    Returns:
        The serialised monitor.

    Raises:
        ResourceNotFoundError: When no monitor with *monitor_id*
            exists in the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    monitor = quality_service.get_monitor(factory, monitor_id, workspace_id=workspace_id)
    if monitor is None:
        raise ResourceNotFoundError(f"Quality monitor {monitor_id} not found.")
    return monitor


@router.get("/api/quality/monitors/{monitor_id}")
async def api_get_monitor(request: Request, monitor_id: int) -> dict[str, Any]:
    """Return one monitor with its recent snapshots and anomalies."""
    monitor = await run_sync(_ensure_monitor, request, monitor_id)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    monitor["snapshots"] = await run_sync(
        quality_service.list_snapshots, factory, monitor_id=monitor_id
    )
    monitor["anomalies"] = await run_sync(
        quality_service.list_anomalies,
        factory,
        workspace_id=workspace_id,
        monitor_id=monitor_id,
    )
    return monitor


@router.patch("/api/quality/monitors/{monitor_id}", dependencies=[Depends(require_admin)])
async def api_update_monitor(
    request: Request,
    monitor_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch target / cron / active flag (admin only).

    Args:
        request: Incoming FastAPI request.
        monitor_id: Monitor id from the URL.
        body: Any of ``{"target", "cron_expr", "is_active"}``.

    Returns:
        The serialised refreshed monitor.
    """
    await run_sync(_ensure_monitor, request, monitor_id)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    updated = await run_sync(
        quality_service.update_monitor,
        factory,
        monitor_id,
        workspace_id=workspace_id,
        target=body.get("target") if isinstance(body.get("target"), str) else None,
        cron_expr=body.get("cron_expr") if isinstance(body.get("cron_expr"), str) else None,
        is_active=bool(body["is_active"]) if "is_active" in body else None,
    )
    assert updated is not None  # ensured above  # noqa: S101
    await audit(
        request,
        "quality_monitor.updated",
        f"quality_monitor:{monitor_id}",
        {"fields": sorted(body)},
    )
    return updated


@router.delete("/api/quality/monitors/{monitor_id}", dependencies=[Depends(require_admin)])
async def api_delete_monitor(request: Request, monitor_id: int) -> dict[str, Any]:
    """Delete a monitor with its snapshots, anomalies, and backing job."""
    await run_sync(_ensure_monitor, request, monitor_id)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    deleted = await run_sync(
        quality_service.delete_monitor, factory, monitor_id, workspace_id=workspace_id
    )
    if deleted:
        await audit(
            request,
            "quality_monitor.deleted",
            f"quality_monitor:{monitor_id}",
            {"id": monitor_id},
        )
    return {"deleted": deleted}


@router.post("/api/quality/monitors/{monitor_id}/run", dependencies=[Depends(require_admin)])
async def api_run_monitor(request: Request, monitor_id: int) -> dict[str, Any]:
    """Scan a monitor now through the scheduler (admin only).

    Materialises the backing job when the monitor never had one
    (created inactive) and dispatches the same ``execute_run`` path
    the cron tick uses, stamped ``trigger="manual"``.

    Args:
        request: Incoming FastAPI request.
        monitor_id: Monitor id from the URL.

    Returns:
        The terminal run record (``run_id`` / ``status`` / ``error``).

    Raises:
        ValidationError: When the backing job cannot be materialised
            (the monitor vanished between lookup and run).
    """
    await run_sync(_ensure_monitor, request, monitor_id)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    job_id = await run_sync(
        quality_service.ensure_backing_job, factory, monitor_id, workspace_id=workspace_id
    )
    if job_id is None:
        raise ValidationError(f"Quality monitor {monitor_id} has no backing job.")
    settings = request.app.state.settings
    run = await scheduler_service.execute_run(
        factory, settings, _QUALITY_REGISTRY, job_id, "manual"
    )
    await audit(
        request,
        "quality_monitor.ran",
        f"quality_monitor:{monitor_id}",
        {"run_id": run.id, "status": run.status},
    )
    return {"run_id": run.id, "status": run.status, "error": run.error}


@router.get("/api/quality/anomalies")
async def api_list_anomalies(
    request: Request,
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
) -> dict[str, Any]:
    """List the workspace's anomalies, optionally filtered by status.

    Args:
        request: Incoming FastAPI request.
        status: ``"open"``, ``"resolved"``, or omitted for both.

    Returns:
        ``{"anomalies": [...]}`` newest-detected first.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    anomalies = await run_sync(
        quality_service.list_anomalies,
        factory,
        workspace_id=workspace_id,
        status=status,
    )
    return {"anomalies": anomalies}


@router.get("/quality", response_class=HTMLResponse)
async def quality_page(request: Request):
    """Render the data-quality cockpit (monitor table + anomaly timeline)."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    monitors = await run_sync(quality_service.list_monitors, factory, workspace_id=workspace_id)
    return get_templates(request).TemplateResponse(
        request,
        "pages/quality.html",
        {
            "active_page": "quality",
            "monitors": monitors,
            "is_admin": bool(user["is_admin"]),
        },
    )
