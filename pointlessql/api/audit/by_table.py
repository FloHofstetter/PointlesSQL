"""HTML + JSON cockpit for "runs by table" reverse-index.

Forward direction lives on the run-detail page (its
``tables_touched`` row).  This module flips the question: given a
table FQN, which runs touched / wrote / read it?  Backed by
:mod:`pointlessql.services.audit.by_table`.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import require_auditor
from pointlessql.exceptions import ValidationError
from pointlessql.services.audit import by_table as audit_by_table

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _parse_iso8601(name: str, value: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 query-string param; coerce naive → UTC.

    Args:
        name: Parameter name for the error message.
        value: Raw query value.

    Returns:
        Parsed ``datetime`` or ``None`` when unset.

    Raises:
        ValidationError: Non-empty ``value`` failed to parse.
    """
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


@router.get("/api/audit/by-table")
async def api_audit_by_table(
    request: Request,
    fqn: str = Query(..., description="Three-part UC name"),
    kind: str = Query(default="touched", description="touched|written|read"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    """Reverse-index "runs by table" — JSON for the cockpit.

    Args:
        request: Incoming FastAPI request.
        fqn: Three-part UC identifier (``catalog.schema.table``)
            matched verbatim.
        kind: Relationship axis — ``touched`` (declared in the
            run's ``tables_touched`` JSON), ``written`` (op or
            value-change against the table), ``read``
            (referenced via ``query_history``).
        since: ISO-8601 lower bound on ``AgentRun.started_at``.
        until: ISO-8601 upper bound (exclusive).
        limit: Hard row cap (1–500).

    Returns:
        ``{"fqn", "kind", "since", "until", "limit", "row_count",
        "runs": [...]}`` with serialised :class:`AgentRun` rows
        newest-first.

    Raises:
        ValidationError: ``kind`` outside the whitelist or
            ``since``/``until`` not ISO-8601.
    """
    require_auditor(request)
    if kind not in audit_by_table.VALID_KINDS:
        raise ValidationError(f"kind must be one of {sorted(audit_by_table.VALID_KINDS)}")
    fqn_clean = fqn.strip()
    if not fqn_clean:
        raise ValidationError("fqn is required")
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)

    runs = audit_by_table.runs_by_table(
        request.app.state.session_factory,
        fqn=fqn_clean,
        kind=kind,  # type: ignore[arg-type]
        since=since_dt,
        until=until_dt,
        limit=limit,
    )
    return {
        "fqn": fqn_clean,
        "kind": kind,
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "limit": limit,
        "row_count": len(runs),
        "runs": runs,
    }


@router.get("/audit/by-table", response_class=HTMLResponse)
async def html_audit_by_table_picker(request: Request) -> HTMLResponse:
    """Render the table-picker variant when no FQN is in the URL.

    Without an FQN there is nothing to query — firing the loaders
    against an empty path was the source of BUG-37-05 (three
    user-visible "Error 422" messages on page load).  This entry
    renders an FQN input form instead so the user can pick a
    target without seeing the chrome's broken loaders.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Rendered ``pages/audit_by_table.html`` with ``table_fqn=""``.
    """
    require_auditor(request)
    return _templates(request).TemplateResponse(
        request,
        "pages/audit_by_table.html",
        {
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "table_fqn": "",
            "kinds": [],
        },
    )


@router.get("/audit/by-table/{fqn:path}", response_class=HTMLResponse)
async def html_audit_by_table(request: Request, fqn: str) -> HTMLResponse:
    """Render the reverse-index page for one table.

    The table's three sub-axes (touched / written / read) load via
    fetch from the JSON endpoint; the server renders only the
    page shell.  ``fqn:path`` allows dotted FQNs like
    ``main.silver.orders`` to land in the route parameter without
    URL encoding.

    Args:
        request: Incoming FastAPI request.
        fqn: Three-part UC identifier from the URL.

    Returns:
        Rendered ``pages/audit_by_table.html``; redirects empty
        ``fqn`` (e.g. ``/audit/by-table/``) to the picker so the
        chrome's loaders don't fire against an empty path.
    """
    require_auditor(request)
    if not fqn or not fqn.strip():
        return _templates(request).TemplateResponse(
            request,
            "pages/audit_by_table.html",
            {
                "active_page": "audit",
                "active_catalog": None,
                "active_schema": None,
                "active_table": None,
                "table_fqn": "",
                "kinds": [],
            },
        )
    return _templates(request).TemplateResponse(
        request,
        "pages/audit_by_table.html",
        {
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "table_fqn": fqn,
            "kinds": ["touched", "written", "read"],
        },
    )
