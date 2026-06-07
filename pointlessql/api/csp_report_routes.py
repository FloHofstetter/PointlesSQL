"""Content-Security-Policy violation report collector.

Browsers POST CSP violation reports to the ``report-uri`` named in the
report-only policy (see :mod:`pointlessql.api.security_headers_middleware`).
This unauthenticated endpoint accepts those reports and logs them so the
policy can be tightened against real evidence before it is enforced.

The route is public-by-design (it lives under ``/api/`` so the CSRF
middleware skips it, and ``/api/csp-report`` is in ``PUBLIC_PREFIXES`` so the
auth middleware lets the browser's credential-less POST through).  It always
returns ``204`` and never raises — a report endpoint must never become a
source of errors itself.  Persisting reports to the audit log is a follow-up;
for now they go to the structured logger.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["security"])


@router.post("/api/csp-report", include_in_schema=False)
async def collect_csp_report(request: Request) -> Response:
    """Accept a browser CSP violation report and log it.

    Args:
        request: The report POST; body is the browser's CSP report JSON
            (``application/csp-report`` or ``application/json``).

    Returns:
        An empty ``204`` response.
    """
    try:
        payload: Any = await request.json()
    except Exception:  # noqa: BLE001 — a malformed report must not 500
        payload = None
    report = None
    if isinstance(payload, dict):
        report = payload.get("csp-report", payload)
    if report:
        logger.warning(
            "csp-report violated-directive=%s blocked-uri=%s document-uri=%s",
            report.get("violated-directive") if isinstance(report, dict) else None,
            report.get("blocked-uri") if isinstance(report, dict) else None,
            report.get("document-uri") if isinstance(report, dict) else None,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
