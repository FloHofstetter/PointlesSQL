"""HTML + JSON cockpit for cross-axis audit search (Phase 18.7).

``GET /api/audit/search`` returns the FTS5 result as JSON for
machine + Hermes consumers.  ``GET /audit/search`` renders the
search page that calls the JSON endpoint via fetch().
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
from pointlessql.services import audit_fts

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


@router.get("/api/audit/search")
async def api_audit_search(
    request: Request,
    q: str = Query(..., min_length=1, description="Free-text query"),
    axis: str = Query(default="all", description="runs|ops|queries|tool_calls|audit_log|all"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Free-text search across the audit lake.

    Backed by SQLite FTS5 on a single virtual table populated by
    triggers (Phase 18.7 alembic migration ``y5u7v9w1x3z5``).
    Postgres deployments return ``available=false`` because the
    migration is SQLite-only.

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
        limit: Max rows (1–500); FTS rank-ascending.

    Returns:
        ``{"available": bool, "query", "axis", "since", "until",
        "limit", "results": [{"axis", "entity_id", "run_id",
        "principal", "table_fqn", "snippet", "rank"}, ...],
        "total_count": int}``.

    Raises:
        ValidationError: ``axis`` outside the whitelist or
            ``since``/``until`` not ISO-8601.
    """
    require_auditor(request)
    if axis not in audit_fts.VALID_AXES:
        raise ValidationError(f"axis must be one of {sorted(audit_fts.VALID_AXES)}")
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    return audit_fts.search(
        request.app.state.session_factory,
        query=q,
        axis=axis,  # type: ignore[arg-type]
        since=since_dt,
        until=until_dt,
        limit=limit,
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
    return _templates(request).TemplateResponse(
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
