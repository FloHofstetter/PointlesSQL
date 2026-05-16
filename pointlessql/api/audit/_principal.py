"""Per-principal audit summary endpoint.

Standalone because the only consumer is the compliance flow
"which runs did <principal> drive last quarter, and what tables did
they touch?".  Splitting it out keeps the metric routes free of the
``AgentRun`` ORM join that this endpoint needs.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from pointlessql.api.audit._helpers import parse_iso8601, record_self
from pointlessql.api.dependencies import require_auditor
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.models import AgentRun
from pointlessql.services import audit_aggregator as agg

router = APIRouter(tags=["audit"])


@router.get("/api/audit/principal-summary", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_principal_summary(
    request: Request,
    principal: str = Query(..., description="AgentRun.principal exact match"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    limit: int = Query(default=20, ge=1, le=200, description="Cap on returned runs"),
) -> dict[str, Any]:
    """Per-principal activity summary.

    Compliance questions like "which runs did <principal> drive last
    quarter, and what tables did they touch?" need this shape.  The
    five per-run audit axes from  give the deep-dive once
    a run is identified, but enumerating runs by principal across a
    window was missing.

    Aggregates :class:`AgentRun` rows for the principal in the window
    and returns headline counts plus the most recent ``limit`` runs
    (newest first).

    Args:
        request: Incoming FastAPI request.
        principal: Exact match against ``AgentRun.principal``.
        since: ISO-8601 lower bound on ``AgentRun.started_at``.
        until: ISO-8601 upper bound (exclusive).
        limit: Max number of run rows to return (default 20).

    Returns:
        ``{"principal", "since", "until", "counts": {...,
        matched_runs: int}, "runs": [...]}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)

    factory = request.app.state.session_factory
    counts = agg.summary(
        factory,
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=None,
        table=None,
    )

    with factory() as session:
        stmt = select(AgentRun).where(AgentRun.principal == principal)
        if since_dt is not None:
            stmt = stmt.where(AgentRun.started_at >= since_dt)
        if until_dt is not None:
            stmt = stmt.where(AgentRun.started_at < until_dt)
        stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
        runs_rows = list(session.scalars(stmt).all())
        run_count_stmt = select(func.count(AgentRun.id)).where(AgentRun.principal == principal)
        if since_dt is not None:
            run_count_stmt = run_count_stmt.where(AgentRun.started_at >= since_dt)
        if until_dt is not None:
            run_count_stmt = run_count_stmt.where(AgentRun.started_at < until_dt)
        total_runs = int(session.scalar(run_count_stmt) or 0)
        runs_payload = [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "started_at": r.started_at.astimezone(datetime.UTC).isoformat(),
                "finished_at": (
                    r.finished_at.astimezone(datetime.UTC).isoformat() if r.finished_at else None
                ),
                "status": r.status,
                "tables_touched": r.tables_touched,
            }
            for r in runs_rows
        ]

    response = {
        "principal": principal,
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "counts": {**counts, "matched_runs": total_runs},
        "runs": runs_payload,
    }
    record_self(
        request,
        endpoint="/api/audit/principal-summary",
        params={
            "principal": principal,
            "since": since,
            "until": until,
            "limit": limit,
        },
        started_at=started_at,
    )
    return response
