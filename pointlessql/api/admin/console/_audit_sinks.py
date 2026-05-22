"""``GET /admin/audit-sinks`` — audit-sink admin page."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin

router = APIRouter(tags=["admin"])


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
    from pointlessql.models.audit._sinks import AuditSink

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

    return get_templates(request).TemplateResponse(
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
