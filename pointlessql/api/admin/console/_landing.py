"""``GET /admin`` — admin landing card-grid."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin
from pointlessql.services._executor import run_sync

router = APIRouter(tags=["admin"])


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request) -> HTMLResponse:
    """Render the admin landing card-grid.

    Aggregates a small set of inexpensive COUNT queries so each
    card can render a glance-level badge (active workspace count,
    active sink/destination counts, unacknowledged external-write
    queue depth).  No joins, no heavy reads — the page must stay
    fast enough that admins return to it as a hub between tasks.
    """
    from sqlalchemy import func
    from sqlalchemy import select as _select

    from pointlessql.models import ApiKey, CdfTailSubscription, Workspace
    from pointlessql.models.agent._reviews import ReviewDestination
    from pointlessql.models.audit._sinks import AuditSink
    from pointlessql.services import external_write_scanner

    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        active_workspaces = (
            session.scalar(_select(func.count(Workspace.id)).where(Workspace.archived_at.is_(None)))
            or 0
        )
        active_sinks = (
            session.scalar(_select(func.count(AuditSink.id)).where(AuditSink.is_active.is_(True)))
            or 0
        )
        active_destinations = (
            session.scalar(
                _select(func.count(ReviewDestination.id)).where(
                    ReviewDestination.is_active.is_(True)
                )
            )
            or 0
        )
        active_api_keys = (
            session.scalar(_select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))) or 0
        )
        active_cdf_subscriptions = (
            session.scalar(
                _select(func.count(CdfTailSubscription.id)).where(
                    CdfTailSubscription.is_active.is_(True)
                )
            )
            or 0
        )
        cdf_subscriptions_with_errors = (
            session.scalar(
                _select(func.count(CdfTailSubscription.id)).where(
                    CdfTailSubscription.last_error.is_not(None)
                )
            )
            or 0
        )

    unacknowledged_external_writes = await run_sync(
        external_write_scanner.count_unacknowledged, factory
    )

    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_index.html",
        {
            "active_workspaces": active_workspaces,
            "active_sinks": active_sinks,
            "active_destinations": active_destinations,
            "active_api_keys": active_api_keys,
            "active_cdf_subscriptions": active_cdf_subscriptions,
            "cdf_subscriptions_with_errors": cdf_subscriptions_with_errors,
            "unacknowledged_external_writes": unacknowledged_external_writes,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
