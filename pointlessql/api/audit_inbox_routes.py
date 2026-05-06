"""HTML cockpit for the cross-run anomaly inbox.

Renders ``pages/audit_inbox.html`` against the same backbone the
``GET /api/audit/inbox`` endpoint exposes.  The page does its own
fetch + ack POST/DELETE round-trips client-side (one tiny inline
script) so the inbox stays interactive without HTMX or Alpine
glue.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import require_auditor
from pointlessql.services import audit_aggregator as agg

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the app-wide Jinja2 templates instance."""
    return request.app.state.templates


@router.get("/audit/inbox", response_class=HTMLResponse)
async def html_audit_inbox(request: Request) -> HTMLResponse:
    """Render the anomaly inbox page.

    The page itself is server-rendered as a thin shell — anomaly
    rows + ack actions arrive via fetch from the client side so the
    same interactions also work for an unauthenticated tester
    pasting curl commands.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Rendered ``pages/audit_inbox.html`` with the metric +
        severity whitelists pre-populated for the filter bar.
    """
    require_auditor(request)
    context: dict[str, Any] = {
        "active_page": "audit",
        "active_catalog": None,
        "active_schema": None,
        "active_table": None,
        "valid_metrics": sorted(agg.VALID_METRICS),
        "run_anomaly_metrics": list(agg.RUN_ANOMALY_METRICS),
        "valid_bins": sorted(agg.VALID_BINS),
    }
    return _templates(request).TemplateResponse(
        request,
        "pages/audit_inbox.html",
        context,
    )
