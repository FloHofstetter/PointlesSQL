"""HTML + JSON cockpit for cross-axis audit search.

``GET /api/audit/search`` returns the FTS5 result as JSON for
machine + Hermes consumers.  ``GET /audit/search`` renders the
search page that calls the JSON endpoint via fetch().
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    PaginationParams,
    get_templates,
    pagination,
    require_auditor,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services import audit_fts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


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


@router.get("/api/audit/search")
async def api_audit_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Free-text query"),
    axis: str = Query(default="all", description="runs|ops|queries|tool_calls|audit_log|all"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    paging: PaginationParams = Depends(pagination),
    kind: str | None = Query(
        default=None,
        description="Polymorphic entity kind (dp|table|model|branch|…)",
    ),
) -> dict[str, Any]:
    """Free-text search across the audit lake.

    Backed by SQLite FTS5 on a single virtual table populated by
    triggers (alembic migration ``y5u7v9w1x3z5``).  Postgres
    deployments use the ``audit_search_index`` GIN-on-tsvector table
    instead.  Both dialects honor ``offset`` so the cockpit can
    stream pages.

    Args:
        request: Incoming FastAPI request.
        q: Free-text query.  FTS5-reserved punctuation
            (parens, double quotes, asterisks) is space-replaced
            before forwarding; dot/underscore/hyphen survive so
            UC FQNs match component-wise.
        axis: Restrict to one axis or ``all``.
        since: ISO-8601 lower bound on the source row's primary
            timestamp (per-axis JOIN).  ``None`` is "no bound".
        until: ISO-8601 upper bound (exclusive).
        paging: Shared offset/limit pagination dep (defaults
            offset=0, limit=100, max 1000).
        kind: Restrict to a polymorphic entity kind (Phase 78
            polish).  Only the ``audit_log`` axis carries a
            kind discriminator; filtering on other axes narrows
            to zero rows.  ``None`` keeps the filter off.

    Returns:
        ``{"available", "query", "axis", "since", "until", "limit",
        "offset", "next_offset", "results", "total_count"}``.
        ``next_offset`` is ``None`` when the page is the tail of the
        result set.

    Raises:
        ValidationError: ``axis`` outside the whitelist or
            ``since``/``until`` not ISO-8601.
    """
    require_auditor(request)
    if axis not in audit_fts.VALID_AXES:
        raise ValidationError(f"axis must be one of {sorted(audit_fts.VALID_AXES)}")
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    return audit_fts.search(
        request.app.state.session_factory,
        query=q,
        axis=axis,  # type: ignore[arg-type]
        since=since_dt,
        until=until_dt,
        limit=paging.limit,
        offset=paging.offset,
        workspace_id=workspace_id,
        kind=kind,
    )


@router.get("/audit/search", response_class=HTMLResponse)
async def html_audit_search(request: Request) -> HTMLResponse:
    """Render the search page.

    The page is a thin shell — search results arrive via fetch
    against ``/api/audit/search`` so the same query also works
    from curl.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Rendered ``pages/audit_search.html``.
    """
    require_auditor(request)
    available = audit_fts.is_available(request.app.state.session_factory)
    return get_templates(request).TemplateResponse(
        request,
        "pages/audit_search.html",
        {
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "fts_available": available,
            "valid_axes": ["all", "runs", "ops", "queries", "tool_calls", "audit_log"],
        },
    )
