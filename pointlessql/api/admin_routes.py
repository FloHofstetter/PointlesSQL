"""Admin audit-log viewer + export.

Owns the two admin-gated routes that surface the ``audit_log``
table:

* ``GET /admin/audit`` (HTML) — filterable list view with a
  1000-row newest-first cap and the same chip-filter Alpine
  component the ``/jobs`` page uses, so search / sort / mobile
  stacking come for free.
* ``GET /admin/audit/export`` — JSON or CSV stream of the same
  filter surface, capped at 10 000 rows per call.  Operators
  wanting more paginate by shrinking the time window.

Audit rows are append-only — every admin state change writes via
``audit()`` from ``api/_audit_helpers.py``.  This module only
reads.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import get_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

ADMIN_AUDIT_LIMIT = 1000
ADMIN_AUDIT_SINCE_WINDOWS: dict[str, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}

AUDIT_EXPORT_LIMIT = 10_000


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_index(
    request: Request,
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> HTMLResponse:
    """Render the admin audit-log viewer.

    Reads from the ``audit_log`` table (written append-only by
    every admin state-change via :func:`audit`) and shows the
    newest :data:`ADMIN_AUDIT_LIMIT` rows matching the requested
    filters. Admin-gated because the log carries cross-user activity
    that a non-admin principal must not see. Re-uses the ``/jobs``
    ``listTable`` Alpine component for search and chip filtering so
    the page inherits sorting, search, and mobile stacking without
    new frontend primitives.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    require_admin(request)
    current_user = get_user(request)
    factory = request.app.state.session_factory

    since_delta = ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    # Fetch one extra row so we can tell the page whether the
    # ``ADMIN_AUDIT_LIMIT`` cap hid older history.
    stmt = stmt.limit(ADMIN_AUDIT_LIMIT + 1)

    with factory() as session:
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)

    truncated = len(rows) > ADMIN_AUDIT_LIMIT
    if truncated:
        rows = rows[:ADMIN_AUDIT_LIMIT]

    entries = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "target": r.target,
            "client_ip": r.client_ip,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
    # Distinct action list for the server-side filter dropdown.
    # Derived from the currently-loaded page so new actions show up
    # automatically; the 1000-row cap keeps this cheap.
    distinct_actions = sorted({e["action"] for e in entries})

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_audit.html",
        {
            "entries": entries,
            "distinct_actions": distinct_actions,
            "filter_action": action or "",
            "filter_user": user or "",
            "filter_target": target or "",
            "filter_since": since,
            "truncated": truncated,
            "row_limit": ADMIN_AUDIT_LIMIT,
            "current_user_id": current_user.get("id"),
            "current_user_email": current_user.get("email"),
            "active_page": "admin_audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@router.get("/admin/audit/export")
async def admin_audit_export(
    request: Request,
    fmt: Literal["json", "csv"] = "json",
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> Response:
    """Stream the filtered audit log as JSON or CSV.

    Mirrors the :func:`admin_audit_index` filter surface so
    operators can "what you see is what you export" from the same
    query string — just swap ``/admin/audit?…`` for
    ``/admin/audit/export?fmt=csv&…``.  Capped at
    :data:`AUDIT_EXPORT_LIMIT` rows per call so a broad ``since=all``
    query cannot blow memory; operators wanting more paginate by
    shrinking the time window.

    Args:
        request: The incoming HTTP request (used for admin gate).
        fmt: ``json`` or ``csv``.
        action: Optional exact-match action filter.
        user: Optional ``ILIKE %…%`` filter on ``user_email``.
        target: Optional ``ILIKE %…%`` filter on ``target``.
        since: Time-window preset (same as the HTML viewer).

    Returns:
        Response: Content-Disposition-attachment response; the
            download filename embeds the export timestamp.
    """
    import csv
    import io

    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    require_admin(request)
    factory = request.app.state.session_factory

    since_delta = ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    stmt = stmt.limit(AUDIT_EXPORT_LIMIT)

    def _rows() -> list[dict[str, Any]]:
        with factory() as session:
            result = list(session.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "user_id": r.user_id,
                "user_email": r.user_email,
                "actor_role": r.actor_role,
                "action": r.action,
                "target": r.target,
                "client_ip": r.client_ip or "",
                "detail": r.detail or "",
            }
            for r in result
        ]

    rows = await asyncio.to_thread(_rows)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if fmt == "json":
        body = json.dumps({"exported_at": timestamp, "entries": rows}, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": (f'attachment; filename="pql-audit-{timestamp}.json"'),
            },
        )

    # CSV
    buf = io.StringIO()
    columns = [
        "id",
        "created_at",
        "user_id",
        "user_email",
        "actor_role",
        "action",
        "target",
        "client_ip",
        "detail",
    ]
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (f'attachment; filename="pql-audit-{timestamp}.csv"'),
        },
    )
