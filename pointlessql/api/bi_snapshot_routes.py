"""Refresh-schedule + snapshot routes for the BI dashboards.

JSON surface for one dashboard's cron schedule (``GET``/``PUT``/
``DELETE …/schedule``) and its captured snapshots (``POST``/``GET``
``…/snapshots``), plus the read-only snapshot HTML page.

Everything here is owner/admin-gated — snapshots are rendered with
the *scheduling* user's privileges, so exposing them to every viewer
would bypass the per-viewer SELECT enforcement the live dashboard
applies.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, Response

from pointlessql.api.bi_dashboards_routes._shared import (
    ensure_can_edit,
    ensure_dashboard,
    serialize_dashboard,
)
from pointlessql.api.dependencies import get_templates
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.services import bi_snapshot_csv
from pointlessql.services import bi_snapshots as snapshot_service

router = APIRouter(tags=["bi-snapshots"])


@router.get("/api/bi/dashboards/{slug}/schedule")
async def api_get_schedule(request: Request, slug: str) -> dict[str, Any]:
    """Return the dashboard's refresh schedule (owner/admin only).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.

    Returns:
        ``{"schedule": {...}}``, or ``{"schedule": None}`` for an
        unscheduled dashboard — the modal prefers an empty form over
        a 404 round-trip.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    row = snapshot_service.get_schedule(
        request.app.state.session_factory, dashboard_id=dashboard.id
    )
    return {"schedule": snapshot_service.serialize_schedule(row) if row else None}


@router.put("/api/bi/dashboards/{slug}/schedule")
async def api_put_schedule(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Create or replace the dashboard's refresh schedule.

    The backing scheduler job is materialised / re-synced in the same
    transaction; an invalid cron expression propagates the service's
    ``ValidationError`` (HTTP 400).

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        body: ``{"cron_expr", "is_active"?, "deliver_inapp"?,
            "webhook_url"?, "webhook_hmac_secret"?}``.  Omitting
            ``webhook_hmac_secret`` keeps the stored secret.

    Returns:
        ``{"schedule": {...}}`` with the persisted state.
    """
    dashboard = ensure_dashboard(request, slug)
    user = ensure_can_edit(request, dashboard)
    secret_kwargs: dict[str, Any] = {}
    if "webhook_hmac_secret" in body:
        raw_secret = body.get("webhook_hmac_secret")
        secret_kwargs["webhook_hmac_secret"] = str(raw_secret) if raw_secret else None
    row = snapshot_service.upsert_schedule(
        request.app.state.session_factory,
        dashboard_id=dashboard.id,
        workspace_id=int(dashboard.workspace_id),
        created_by_user_id=int(user["id"]),
        cron_expr=str(body.get("cron_expr") or ""),
        is_active=bool(body.get("is_active", True)),
        deliver_inapp=bool(body.get("deliver_inapp", True)),
        webhook_url=str(body.get("webhook_url") or "").strip() or None,
        **secret_kwargs,
    )
    return {"schedule": snapshot_service.serialize_schedule(row)}


@router.delete("/api/bi/dashboards/{slug}/schedule")
async def api_delete_schedule(request: Request, slug: str) -> dict[str, Any]:
    """Delete the dashboard's schedule plus its backing job.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.

    Returns:
        ``{"deleted": True}``.

    Raises:
        ResourceNotFoundError: When the dashboard has no schedule.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    deleted = snapshot_service.delete_schedule(
        request.app.state.session_factory, dashboard_id=dashboard.id
    )
    if not deleted:
        raise ResourceNotFoundError(f"Dashboard '{slug}' has no schedule.")
    return {"deleted": True}


@router.post("/api/bi/dashboards/{slug}/snapshots")
async def api_create_snapshot(request: Request, slug: str) -> dict[str, Any]:
    """Capture a snapshot now, as the calling principal.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.

    Returns:
        ``{"id", "url"}`` of the new snapshot.
    """
    dashboard = ensure_dashboard(request, slug)
    user = ensure_can_edit(request, dashboard)
    snapshot_id = await snapshot_service.render_snapshot(
        request.app.state.session_factory,
        uc_client=request.app.state.uc_client,
        dashboard_id=dashboard.id,
        workspace_id=int(dashboard.workspace_id),
        actor_email=user["email"],
        is_admin=bool(user["is_admin"]),
        triggered_by="manual",
    )
    return {"id": snapshot_id, "url": f"/bi/{slug}/snapshots/{snapshot_id}"}


@router.get("/api/bi/dashboards/{slug}/snapshots")
async def api_list_snapshots(request: Request, slug: str) -> dict[str, Any]:
    """List the dashboard's snapshots, newest first.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.

    Returns:
        ``{"snapshots": [{"id", "captured_at", "triggered_by",
        "widget_count"}]}``.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    return {
        "snapshots": snapshot_service.list_snapshots(
            request.app.state.session_factory, dashboard_id=dashboard.id
        )
    }


def _ensure_snapshot(request: Request, slug: str, snapshot_id: int) -> dict[str, Any]:
    """Resolve one snapshot behind the owner/admin gate, or 404.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        snapshot_id: Snapshot primary key.

    Returns:
        ``{"dashboard": <serialized>, "id", "captured_at",
        "triggered_by", "payload": <parsed dict>}``.

    Raises:
        ResourceNotFoundError: When the snapshot is not on this
            dashboard.
    """
    dashboard = ensure_dashboard(request, slug)
    ensure_can_edit(request, dashboard)
    row = snapshot_service.get_snapshot(
        request.app.state.session_factory,
        dashboard_id=dashboard.id,
        snapshot_id=snapshot_id,
    )
    if row is None:
        raise ResourceNotFoundError(f"Snapshot {snapshot_id} not found on '{slug}'.")
    return {
        "dashboard": serialize_dashboard(dashboard),
        "id": row.id,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "triggered_by": row.triggered_by,
        "payload": json.loads(row.payload),
    }


@router.get("/api/bi/dashboards/{slug}/snapshots/{snapshot_id}")
async def api_get_snapshot(request: Request, slug: str, snapshot_id: int) -> dict[str, Any]:
    """Return one snapshot's full payload.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        snapshot_id: Snapshot primary key.

    Returns:
        ``{"id", "captured_at", "triggered_by", "payload"}``.
    """
    resolved = _ensure_snapshot(request, slug, snapshot_id)
    return {
        "id": resolved["id"],
        "captured_at": resolved["captured_at"],
        "triggered_by": resolved["triggered_by"],
        "payload": resolved["payload"],
    }


@router.get("/api/bi/dashboards/{slug}/snapshots/{snapshot_id}/csv", response_class=Response)
async def api_get_snapshot_csv(request: Request, slug: str, snapshot_id: int) -> Response:
    """Download a snapshot's data-backed widgets as a CSV attachment.

    The same tabular CSV a scheduled subscription would attach — one
    section per data-backed widget.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        snapshot_id: Snapshot primary key.

    Returns:
        A ``text/csv`` attachment response.
    """
    resolved = _ensure_snapshot(request, slug, snapshot_id)
    csv_text = bi_snapshot_csv.snapshot_to_csv(resolved["payload"])
    filename = f"{slug}-snapshot-{snapshot_id}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bi/{slug}/snapshots/{snapshot_id}", response_class=HTMLResponse)
async def bi_snapshot_page(request: Request, slug: str, snapshot_id: int) -> HTMLResponse:
    """Render the read-only snapshot page (owner/admin only).

    No SQL runs here — every widget paints from the frozen payload,
    which is exactly the point of a snapshot.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        snapshot_id: Snapshot primary key.

    Returns:
        The rendered snapshot page.
    """
    resolved = _ensure_snapshot(request, slug, snapshot_id)
    return get_templates(request).TemplateResponse(
        request,
        "pages/bi_snapshot.html",
        {
            "active_page": "bi",
            "dashboard": resolved["dashboard"],
            "snapshot": {
                "id": resolved["id"],
                "captured_at": resolved["captured_at"],
                "triggered_by": resolved["triggered_by"],
                "payload": resolved["payload"],
            },
        },
    )
