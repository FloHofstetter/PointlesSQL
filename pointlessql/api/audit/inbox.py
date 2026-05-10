"""HTML cockpit for the cross-run anomaly inbox.

Renders ``pages/audit_inbox.html`` against the same backbone the
``GET /api/audit/inbox`` endpoint exposes.  The page does its own
fetch + ack POST/DELETE round-trips client-side (one tiny inline
script) so the inbox stays interactive without HTMX or Alpine
glue.

A second band on the page surfaces *system errors* — currently the
foreign-Delta CDF subscriptions that have ``last_error IS NOT NULL``.
This is point-in-time state (not a sigma-anomaly), so it renders
server-side from the loader rather than via the JSON inbox API.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_auditor
from pointlessql.models import CdfTailSubscription
from pointlessql.services import audit_aggregator as agg

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the app-wide Jinja2 templates instance."""
    return request.app.state.templates


def _load_system_errors(factory: Any, *, workspace_id: int) -> list[dict[str, Any]]:
    """Return CDF subscriptions with a current ``last_error`` for the workspace.

    Point-in-time signal, not a time-binned anomaly: a subscription
    has either a current error or it doesn't, and the next
    successful tail tick clears it (no separate ack table).  The
    inbox renders this band above the sigma anomaly cards so the
    audit-reviewer persona sees broken capture *before* drilling
    into per-bin breaches.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace; only this workspace's
            subscriptions are surfaced.

    Returns:
        One dict per subscription with ``last_error IS NOT NULL``,
        ordered by ``last_tailed_at`` DESC so freshest failures
        bubble to the top.  Empty list when nothing's broken.
    """
    with factory() as session:
        stmt = (
            select(CdfTailSubscription)
            .where(
                CdfTailSubscription.workspace_id == workspace_id,
                CdfTailSubscription.last_error.is_not(None),
            )
            .order_by(CdfTailSubscription.last_tailed_at.desc().nullslast())
        )
        rows = list(session.scalars(stmt))
    return [
        {
            "id": r.id,
            "table_full_name": r.table_full_name,
            "producer_label": r.producer_label,
            "last_error": r.last_error,
            "last_tailed_at": r.last_tailed_at.isoformat() if r.last_tailed_at else None,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.get("/audit/inbox", response_class=HTMLResponse)
async def html_audit_inbox(request: Request) -> HTMLResponse:
    """Render the anomaly inbox page.

    The page itself is server-rendered as a thin shell — anomaly
    rows + ack actions arrive via fetch from the client side so the
    same interactions also work for an unauthenticated tester
    pasting curl commands.  The system-errors band, in contrast,
    renders server-side because CDF subscription health is
    point-in-time state and shouldn't depend on a JS round-trip
    succeeding.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Rendered ``pages/audit_inbox.html`` with the metric +
        severity whitelists pre-populated for the filter bar and
        ``system_errors`` populated from the workspace's CDF
        subscription registry.
    """
    require_auditor(request)
    factory = request.app.state.session_factory
    system_errors = _load_system_errors(factory, workspace_id=current_workspace_id(request))
    context: dict[str, Any] = {
        "active_page": "audit",
        "active_catalog": None,
        "active_schema": None,
        "active_table": None,
        "valid_metrics": sorted(agg.VALID_METRICS),
        "run_anomaly_metrics": list(agg.RUN_ANOMALY_METRICS),
        "valid_bins": sorted(agg.VALID_BINS),
        "system_errors": system_errors,
    }
    return _templates(request).TemplateResponse(
        request,
        "pages/audit_inbox.html",
        context,
    )
