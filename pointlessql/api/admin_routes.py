"""Admin landing page + audit-log viewer + export.

Owns the admin-gated routes that surface the install-global
operator tooling:

* ``GET /admin`` (HTML) — landing card-grid linking to every
  operator surface.  Cheap to render: aggregates a few COUNT
  queries, no joins.
* ``GET /admin/audit`` (HTML) — filterable list view over
  ``audit_log`` with a 1000-row newest-first cap and the same
  chip-filter Alpine component the ``/jobs`` page uses, so
  search / sort / mobile stacking come for free.
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


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request) -> HTMLResponse:
    """Render the admin landing card-grid.

    Aggregates a small set of inexpensive COUNT queries so each
    card can render a glance-level badge (active workspace count,
    active sink/destination counts, unacknowledged external-write
    queue depth).  No joins, no heavy reads — the page must stay
    fast enough that admins return to it as a hub between tasks.
    """
    from sqlalchemy import func
    from sqlalchemy import select as _select

    from pointlessql.models import ApiKey, Workspace
    from pointlessql.models.agent_reviews import ReviewDestination
    from pointlessql.models.audit_sinks import AuditSink
    from pointlessql.services import external_write_scanner

    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        active_workspaces = (
            session.scalar(_select(func.count(Workspace.id)).where(Workspace.archived_at.is_(None)))
            or 0
        )
        active_sinks = (
            session.scalar(_select(func.count(AuditSink.id)).where(AuditSink.is_active.is_(True)))
            or 0
        )
        active_destinations = (
            session.scalar(
                _select(func.count(ReviewDestination.id)).where(
                    ReviewDestination.is_active.is_(True)
                )
            )
            or 0
        )
        active_api_keys = (
            session.scalar(_select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))) or 0
        )

    unacknowledged_external_writes = await asyncio.to_thread(
        external_write_scanner.count_unacknowledged, factory
    )

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_index.html",
        {
            "active_workspaces": active_workspaces,
            "active_sinks": active_sinks,
            "active_destinations": active_destinations,
            "active_api_keys": active_api_keys,
            "unacknowledged_external_writes": unacknowledged_external_writes,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/admin/review-destinations", response_class=HTMLResponse)
async def admin_review_destinations_index(request: Request) -> HTMLResponse:
    """Render the review-destinations management page.

    Reads the full ``review_destinations`` table plus the workspace
    list (so the workspace-filter chips can show slugs rather than
    opaque integer IDs) and renders one row per destination.
    Mutations use the existing ``/api/admin/review-destinations``
    JSON CRUD — nothing new server-side.
    """
    import json as _json

    from sqlalchemy import select as _select

    from pointlessql.models import Workspace
    from pointlessql.models.agent_reviews import REVIEW_SEVERITIES, ReviewDestination

    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        destinations = list(
            session.scalars(_select(ReviewDestination).order_by(ReviewDestination.id.asc())).all()
        )
        for row in destinations:
            session.expunge(row)
        workspaces = list(
            session.scalars(
                _select(Workspace)
                .where(Workspace.archived_at.is_(None))
                .order_by(Workspace.slug.asc())
            ).all()
        )
        for row in workspaces:
            session.expunge(row)

    dest_rows = []
    for dest in destinations:
        try:
            workspace_filter = _json.loads(dest.workspace_filter) if dest.workspace_filter else None
        except _json.JSONDecodeError:
            workspace_filter = None
        dest_rows.append(
            {
                "id": dest.id,
                "name": dest.name,
                "webhook_url": dest.webhook_url,
                "has_hmac_secret": bool(dest.hmac_secret),
                "is_active": bool(dest.is_active),
                "min_severity": dest.min_severity,
                "workspace_filter": workspace_filter
                if isinstance(workspace_filter, list)
                else None,
                "created_at": dest.created_at.isoformat() if dest.created_at else "",
            }
        )

    workspace_choices = [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces]

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_review_destinations.html",
        {
            "destinations": dest_rows,
            "workspace_choices": workspace_choices,
            "severities": sorted(REVIEW_SEVERITIES),
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/admin/audit-sinks", response_class=HTMLResponse)
async def admin_audit_sinks_index(request: Request) -> HTMLResponse:
    """Render the audit-sinks management page.

    Reads the full ``audit_sinks`` table plus the workspace list
    (so the workspace-filter chips can show slugs rather than
    opaque integer IDs) and renders one row per sink.  Mutations
    use the existing ``/api/admin/audit-sinks`` JSON CRUD —
    nothing new server-side.
    """
    import json as _json

    from sqlalchemy import select as _select

    from pointlessql.models import Workspace
    from pointlessql.models.audit_sinks import AuditSink

    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        sinks = list(session.scalars(_select(AuditSink).order_by(AuditSink.id.asc())).all())
        for row in sinks:
            session.expunge(row)
        workspaces = list(
            session.scalars(
                _select(Workspace)
                .where(Workspace.archived_at.is_(None))
                .order_by(Workspace.slug.asc())
            ).all()
        )
        for row in workspaces:
            session.expunge(row)

    sensitive_keys = {"hmac_secret", "secret_access_key", "session_token"}

    def _redact(cfg: dict[str, Any]) -> dict[str, Any]:
        return {k: ("<set>" if k in sensitive_keys and v else v) for k, v in cfg.items()}

    sink_rows = []
    for sink in sinks:
        try:
            cfg = _json.loads(sink.config_json or "{}")
        except _json.JSONDecodeError:
            cfg = {}
        try:
            event_types = _json.loads(sink.event_types_json) if sink.event_types_json else []
        except _json.JSONDecodeError:
            event_types = []
        try:
            workspace_filter = _json.loads(sink.workspace_filter) if sink.workspace_filter else None
        except _json.JSONDecodeError:
            workspace_filter = None
        sink_rows.append(
            {
                "id": sink.id,
                "name": sink.name,
                "type": sink.type,
                "config_redacted": _redact(cfg if isinstance(cfg, dict) else {}),
                "is_active": bool(sink.is_active),
                "event_types": event_types if isinstance(event_types, list) else [],
                "workspace_filter": workspace_filter
                if isinstance(workspace_filter, list)
                else None,
                "created_at": sink.created_at.isoformat() if sink.created_at else "",
            }
        )

    workspace_choices = [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces]

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_audit_sinks.html",
        {
            "sinks": sink_rows,
            "workspace_choices": workspace_choices,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/admin/api-keys", response_class=HTMLResponse)
async def admin_api_keys_index(request: Request, include_revoked: bool = False) -> HTMLResponse:
    """Render the API-keys management page.

    Lists every key (active by default; revoked rows shown when
    ``include_revoked=1``) joined with its workspace so the UI can
    label keys by slug rather than opaque integer ID.  Mutations
    use the existing ``/api/admin/api-keys`` JSON CRUD — nothing
    new server-side beyond the optional ``workspace_id`` field
    accepted at create.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import ApiKey, Workspace

    require_admin(request)
    factory = request.app.state.session_factory

    with factory() as session:
        stmt = _select(ApiKey).order_by(ApiKey.created_at.desc())
        if not include_revoked:
            stmt = stmt.where(ApiKey.revoked_at.is_(None))
        keys = list(session.scalars(stmt).all())
        for row in keys:
            session.expunge(row)
        workspaces = list(
            session.scalars(
                _select(Workspace)
                .where(Workspace.archived_at.is_(None))
                .order_by(Workspace.slug.asc())
            ).all()
        )
        for row in workspaces:
            session.expunge(row)

    workspace_by_id = {w.id: w for w in workspaces}
    key_rows = []
    for k in keys:
        ws = workspace_by_id.get(k.workspace_id)
        key_rows.append(
            {
                "name": k.name,
                "secret_prefix": k.secret_prefix,
                "supervisor": bool(k.supervisor),
                "auditor": bool(k.auditor),
                "lineage_inbound": bool(getattr(k, "lineage_inbound", False)),
                "workspace_id": k.workspace_id,
                "workspace_slug": ws.slug if ws else None,
                "created_at": k.created_at.isoformat() if k.created_at else "",
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
        )

    workspace_choices = [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces]
    default_workspace_id = workspace_choices[0]["id"] if workspace_choices else 1

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_api_keys.html",
        {
            "keys": key_rows,
            "include_revoked": include_revoked,
            "workspace_choices": workspace_choices,
            "default_workspace_id": default_workspace_id,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/admin/system-info", response_class=HTMLResponse)
async def admin_system_info_index(request: Request) -> HTMLResponse:
    """Render the system-info read-only panel.

    Aggregates four read-only sections: PII mode (active enum +
    hash-secret presence), API-key counts (active / revoked /
    supervisor / auditor), OIDC group → workspace + scope mapping
    (parsed from env at startup), and the ``system_keys`` row
    inventory (names + ``created_at`` only — values never rendered).
    Every value is read-only because each control is env-restart-
    gated; surfacing a writable form here would silently desync
    from ``os.environ``.
    """
    from sqlalchemy import func
    from sqlalchemy import select as _select

    from pointlessql.models import ApiKey, Workspace
    from pointlessql.models.system_keys import SystemKey

    require_admin(request)
    settings = request.app.state.settings
    factory = request.app.state.session_factory

    with factory() as session:
        active = (
            session.scalar(_select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))) or 0
        )
        revoked = (
            session.scalar(_select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_not(None)))
            or 0
        )
        supervisor = (
            session.scalar(
                _select(func.count(ApiKey.id)).where(
                    ApiKey.supervisor.is_(True), ApiKey.revoked_at.is_(None)
                )
            )
            or 0
        )
        auditor = (
            session.scalar(
                _select(func.count(ApiKey.id)).where(
                    ApiKey.auditor.is_(True), ApiKey.revoked_at.is_(None)
                )
            )
            or 0
        )

        sk_rows = list(session.scalars(_select(SystemKey).order_by(SystemKey.name.asc())).all())
        for row in sk_rows:
            session.expunge(row)

        pii_hash_row = next((r for r in sk_rows if r.name == "pii_hash"), None)

        workspaces = list(
            session.scalars(
                _select(Workspace)
                .where(Workspace.archived_at.is_(None))
                .order_by(Workspace.slug.asc())
            ).all()
        )
        for row in workspaces:
            session.expunge(row)

    system_keys_view = [
        {"name": k.name, "created_at": k.created_at.isoformat() if k.created_at else ""}
        for k in sk_rows
    ]
    workspace_choices = [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces]
    default_workspace_id = workspace_choices[0]["id"] if workspace_choices else 1

    oidc_settings = settings.oidc
    oidc_group_map_items = sorted(oidc_settings.parsed_group_map.items())

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_system_info.html",
        {
            "pii_mode": settings.audit.pii_mode,
            "pii_mask_default": settings.audit.pii_mask_default,
            "pii_hash_secret_present": pii_hash_row is not None,
            "pii_hash_secret_created_at": (
                pii_hash_row.created_at.isoformat()
                if pii_hash_row and pii_hash_row.created_at
                else None
            ),
            "api_key_count_active": active,
            "api_key_count_revoked": revoked,
            "api_key_count_supervisor": supervisor,
            "api_key_count_auditor": auditor,
            "oidc_enabled": oidc_settings.enabled,
            "oidc_group_map": oidc_group_map_items,
            "system_keys": system_keys_view,
            "workspace_choices": workspace_choices,
            "default_workspace_id": default_workspace_id,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


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

    from pointlessql.api.dependencies import effective_principal, get_user
    from pointlessql.services.governance_events import (
        EVENT_TYPE_AUDIT_EXPORT_ISSUED,
        emit_governance_event,
    )

    requester_user = get_user(request)
    requester_email = effective_principal(request) or requester_user.get("email") or ""
    try:
        await emit_governance_event(
            EVENT_TYPE_AUDIT_EXPORT_ISSUED,
            {
                "principal": requester_email,
                "fmt": fmt,
                "since": since,
                "row_count": len(rows),
                "filter_action": action,
                "filter_user": user,
                "filter_target": target,
                "exported_at": timestamp,
            },
            session_factory=factory,
        )
    except Exception:  # noqa: BLE001 — emit must never raise
        logger.exception("audit_export.issued emit failed at %s", timestamp)

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
