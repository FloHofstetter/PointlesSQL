"""Auditor-scope CDF tail-subscription read endpoints.

Read-only counterparts to the admin-scope
``/api/admin/cdf-subscriptions`` surface.  The Audit-Reviewer-Agent
uses these to surface coverage gaps ("which foreign tables don't have
a tail subscription yet?") and inspect recent CDF events without the
admin's toggle / register / delete affordances.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.audit._helpers import record_self
from pointlessql.api.dependencies import current_workspace_id, require_auditor

router = APIRouter(tags=["audit"])


@router.get("/api/audit/cdf-subscriptions")
async def api_audit_cdf_subscriptions(
    request: Request,
    only_active: bool = Query(default=False, description="When True, omit paused subs"),
) -> dict[str, Any]:
    """List CDF tail subscriptions visible in the caller's workspace.

    Auditor-scope counterpart to the admin-only
    ``GET /api/admin/cdf-subscriptions``.  Reads only — no toggle,
    no register, no delete.  The Audit-Reviewer-Agent uses this to
    surface coverage gaps ("which foreign tables don't have a tail
    subscription yet?").

    Args:
        request: Incoming FastAPI request.
        only_active: When True, omit paused subscriptions.

    Returns:
        ``{"subscriptions": [...]}`` ordered by ``created_at DESC``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    from pointlessql.models import CdfTailSubscription

    with factory() as session:
        stmt = select(CdfTailSubscription).where(CdfTailSubscription.workspace_id == workspace_id)
        if only_active:
            stmt = stmt.where(CdfTailSubscription.is_active.is_(True))
        rows = list(session.scalars(stmt.order_by(CdfTailSubscription.created_at.desc())).all())
        out = [
            {
                "id": r.id,
                "table_full_name": r.table_full_name,
                "row_id_column": r.row_id_column,
                "producer_label": r.producer_label,
                "is_active": bool(r.is_active),
                "last_version_processed": r.last_version_processed,
                "last_tailed_at": r.last_tailed_at.isoformat() if r.last_tailed_at else None,
                "last_error": r.last_error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    response = {"subscriptions": out}
    record_self(
        request,
        endpoint="/api/audit/cdf-subscriptions",
        params={"only_active": only_active},
        started_at=started_at,
    )
    return response


@router.get("/api/audit/cdf-events")
async def api_audit_cdf_events(
    request: Request,
    table: str = Query(..., description="Three-part UC name to read CDF events for"),
    limit: int = Query(default=50, ge=1, le=500, description="Max rows newest-first"),
) -> dict[str, Any]:
    """Read recent foreign-Delta CDF tail events for one table.

    Workspace-scoped: only events captured under the caller's
    current workspace are returned.  Counterpart to the
    table-detail "CDF events" tab; agent / plugin variant.

    Args:
        request: Incoming FastAPI request.
        table: Three-part UC name to read events for.
        limit: Hard cap on returned rows; clamped 1..500 by FastAPI.

    Returns:
        ``{"table", "subscription": {...} | None, "events": [...]}``.
        ``subscription`` is ``None`` when the workspace has no
        registered subscription for the table; ``events`` is then
        always empty.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    from pointlessql.models import CdfTailEvent, CdfTailSubscription

    with factory() as session:
        sub = session.scalars(
            select(CdfTailSubscription).where(
                CdfTailSubscription.workspace_id == workspace_id,
                CdfTailSubscription.table_full_name == table,
            )
        ).first()
        sub_payload: dict[str, Any] | None
        events_payload: list[dict[str, Any]] = []
        if sub is None:
            sub_payload = None
        else:
            sub_payload = {
                "id": sub.id,
                "table_full_name": sub.table_full_name,
                "row_id_column": sub.row_id_column,
                "producer_label": sub.producer_label,
                "is_active": bool(sub.is_active),
                "last_version_processed": sub.last_version_processed,
                "last_tailed_at": sub.last_tailed_at.isoformat() if sub.last_tailed_at else None,
                "last_error": sub.last_error,
            }
            rows = list(
                session.scalars(
                    select(CdfTailEvent)
                    .where(
                        CdfTailEvent.workspace_id == workspace_id,
                        CdfTailEvent.table_full_name == table,
                    )
                    .order_by(CdfTailEvent.created_at.desc())
                    .limit(limit)
                ).all()
            )
            events_payload = [
                {
                    "id": r.id,
                    "delta_version": r.delta_version,
                    "row_id": r.row_id,
                    "change_type": r.change_type,
                    "commit_timestamp": r.commit_timestamp.isoformat()
                    if r.commit_timestamp
                    else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    response = {
        "table": table,
        "subscription": sub_payload,
        "events": events_payload,
    }
    record_self(
        request,
        endpoint="/api/audit/cdf-events",
        params={"table": table, "limit": limit},
        started_at=started_at,
    )
    return response
