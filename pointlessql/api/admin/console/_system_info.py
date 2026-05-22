"""``GET /admin/system-info`` — read-only system info panel."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin

router = APIRouter(tags=["admin"])


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

    return get_templates(request).TemplateResponse(
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
