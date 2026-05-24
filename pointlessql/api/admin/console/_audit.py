"""``/admin/audit*`` — audit-log viewer + JSON/CSV export + tar.gz bundle."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

import pointlessql
from pointlessql.api.admin.console._constants import (
    ADMIN_AUDIT_LIMIT,
    ADMIN_AUDIT_SINCE_WINDOWS,
    AUDIT_EXPORT_LIMIT,
)
from pointlessql.api.dependencies import get_templates, get_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_index(
    request: Request,
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
    offset: int = 0,
) -> HTMLResponse:
    """Render the admin audit-log viewer.

    Reads from the ``audit_log`` table (written append-only by
    every admin state-change via :func:`audit`) and shows
    :data:`ADMIN_AUDIT_LIMIT` rows per page matching the requested
    filters.  Admin-gated because the log carries cross-user activity
    that a non-admin principal must not see.  Re-uses the ``/jobs``
    ``listTable`` Alpine component for search and chip filtering so
    the page inherits sorting, search, and mobile stacking without
    new frontend primitives.

    Phase 54.3 turned the previous single-shot truncation cap into a
    real ``offset``-based pagination: a separate ``COUNT(*)`` query
    drives the page-link footer (Bootstrap 5.3 ``pagination``
    component via ``_macros/pagination.html``).  The client-side
    filter chips operate on the visible page only — same trade-off
    as ``/runs``.
    """
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    require_admin(request)
    current_user = get_user(request)
    factory = request.app.state.session_factory

    if offset < 0:
        offset = 0

    since_delta = ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    base = _select(AuditLogModel)
    if since_cutoff is not None:
        base = base.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        base = base.where(AuditLogModel.action == action)
    if user:
        base = base.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        base = base.where(AuditLogModel.target.ilike(f"%{target}%"))

    count_stmt = _select(_func.count()).select_from(base.subquery())
    page_stmt = (
        base.order_by(AuditLogModel.created_at.desc()).offset(offset).limit(ADMIN_AUDIT_LIMIT)
    )

    with factory() as session:
        total = int(session.scalar(count_stmt) or 0)
        rows = list(session.scalars(page_stmt).all())
        for row in rows:
            session.expunge(row)

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
    # automatically; the per-page cap keeps this cheap.
    distinct_actions = sorted({e["action"] for e in entries})

    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_audit.html",
        {
            "entries": entries,
            "distinct_actions": distinct_actions,
            "filter_action": action or "",
            "filter_user": user or "",
            "filter_target": target or "",
            "filter_since": since,
            "total": total,
            "offset": offset,
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
    from pointlessql.services.workspace.governance import (
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


@router.get("/admin/audit/export.tar.gz")
async def admin_audit_export_tarball(
    request: Request,
    fmt: Literal["json", "csv"] = "json",
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> Response:
    """Stream a ``.tar.gz`` bundle of the export + tamper-evidence sidecars.

    func:`admin_audit_export`;
    the response body is a gzipped tarball containing three files:

    * ``pql-audit-<ts>.<fmt>`` — data.
    * ``pql-audit-<ts>.<fmt>.sha256`` — sha256sum-compatible sidecar.
    * ``pql-audit-<ts>.<fmt>.manifest.json`` — filters + counts +
      tool version + recorded ``data_sha256``.

    Auditors verify the export by:

    1. Extracting the tarball.
    2. Running ``sha256sum -c <out>.sha256``.
    3. Cross-checking the manifest's ``data_sha256`` field.

    Args:
        request: Incoming FastAPI request.
        fmt: ``'json'`` or ``'csv'``.
        action: Optional exact-match action filter.
        user: Optional substring filter on ``user_email``.
        target: Optional substring filter on ``target``.
        since: Time-window preset.

    Returns:
        Response: gzipped tarball as
            ``application/gzip`` with attachment header.
    """
    import io as _io
    import tarfile

    from pointlessql.cli.audit_export import (
        ExportFilters,
        encode_payload,
        serialise_rows,
    )

    require_admin(request)
    factory = request.app.state.session_factory

    since_delta = ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None
    filters = ExportFilters(
        since=since_cutoff,
        until=None,
        action=action,
        actor=user,
        target=target,
    )
    rows = await asyncio.to_thread(serialise_rows, factory, filters)
    exported_at = datetime.now(UTC)
    timestamp = exported_at.strftime("%Y%m%dT%H%M%SZ")
    payload = encode_payload(rows, fmt=fmt, exported_at=exported_at)
    data_name = f"pql-audit-{timestamp}.{fmt}"
    sha = hashlib.sha256(payload).hexdigest()
    sha_body = f"{sha}  {data_name}\n".encode("ascii")
    manifest = {
        "schema_version": "1",
        "tool_version": pointlessql.__version__,
        "exported_at": exported_at.isoformat(),
        "fmt": fmt,
        "filters": filters.to_manifest_dict(),
        "entry_count": len(rows),
        "data_sha256": sha,
        "data_filename": data_name,
    }
    manifest_body = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    buf = _io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for member_name, member_bytes in (
            (data_name, payload),
            (f"{data_name}.sha256", sha_body),
            (f"{data_name}.manifest.json", manifest_body),
        ):
            info = tarfile.TarInfo(name=member_name)
            info.size = len(member_bytes)
            info.mtime = int(exported_at.timestamp())
            info.mode = 0o600
            tar.addfile(info, _io.BytesIO(member_bytes))

    return Response(
        content=buf.getvalue(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": (f'attachment; filename="pql-audit-{timestamp}.tar.gz"'),
        },
    )
