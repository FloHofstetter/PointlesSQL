"""Paginated ``query_history`` slice for audit-trail traversal.

The Audit-Reviewer-Agent and the compliance demo flows use this
endpoint to walk yesterday's activity log without the full SQL-editor
surface.  Default filtering excludes the cockpit's own self-tracking
rows so an agent doesn't page through its own audit-of-audit
breadcrumbs forever.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.audit._helpers import parse_iso8601, record_self
from pointlessql.api.dependencies import require_auditor
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.services.query_history import VALID_READ_KINDS, list_queries

router = APIRouter(tags=["audit"])


@router.get("/api/audit/history", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_history(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    read_kind: str | None = Query(
        default=None,
        description="Filter to a single read_kind; default excludes audit_api to avoid recursion",
    ),
    status: str | None = Query(default=None, description="Filter on query_history.status"),
    limit: int = Query(default=200, ge=1, le=500),
    include_audit_api: bool = Query(
        default=False,
        description="Set true to include audit-of-audit rows; default hides them.",
    ),
) -> dict[str, Any]:
    """Paginated ``query_history`` slice for audit-trail traversal.

    gives the daily Audit-Reviewer-Agent (and the
    compliance / incident demo flows) a way to walk yesterday's
    activity log without the full SQL-editor surface.

    By default the response *excludes* rows whose ``read_kind`` is
    ``audit_api`` (the rows produced by the cockpit endpoints
    themselves, including this route).  Without that filter a
    well-meaning agent would page through its own audit-of-audit
    breadcrumbs forever; admins who do want to inspect the
    cockpit's self-tracking can pass ``?include_audit_api=true`` or
    ``?read_kind=audit_api`` directly.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on ``started_at``.  ``None`` is
            "all-time".
        until: ISO-8601 upper bound (exclusive).  ``None`` is "now".
        read_kind: Single ``read_kind`` filter.  Unknown values fall
            through to "no filter" (matches :func:`list_queries`'s
            tolerance contract).
        status: Filter to a single status value.  ``None`` returns
            all.
        limit: Hard row cap (1–500).
        include_audit_api: When ``False`` (the default) and no
            explicit ``read_kind`` is set, rows with
            ``read_kind='audit_api'`` are filtered out post-query.
            When ``True`` no recursion filter is applied.

    Returns:
        ``{"since", "until", "read_kind", "status", "include_audit_api",
        "limit", "rows": [...], "row_count": int}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)
    factory = request.app.state.session_factory
    rows = list_queries(
        factory,
        since=since_dt,
        read_kind=read_kind,
        status=status,
        limit=limit,
    )
    if until_dt is not None:
        cutoff = until_dt.isoformat()
        rows = [r for r in rows if (r.get("started_at") or "") < cutoff]
    if not include_audit_api and read_kind != "audit_api":
        rows = [r for r in rows if r.get("read_kind") != "audit_api"]
    response: dict[str, Any] = {
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "read_kind": read_kind if read_kind in VALID_READ_KINDS else None,
        "status": status,
        "include_audit_api": include_audit_api,
        "limit": limit,
        "row_count": len(rows),
        "rows": rows,
    }
    record_self(
        request,
        endpoint="/api/audit/history",
        params={
            "since": since,
            "until": until,
            "read_kind": read_kind,
            "status": status,
            "limit": limit,
            "include_audit_api": include_audit_api,
        },
        started_at=started_at,
    )
    return response
