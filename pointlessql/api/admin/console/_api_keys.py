"""``GET /admin/api-keys`` — API-key admin page (HTML)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin
from pointlessql.exceptions import CatalogNotFoundError

router = APIRouter(tags=["admin"])


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
                "analyst": bool(getattr(k, "analyst", False)),
                "sql_execute": bool(getattr(k, "sql_execute", False)),
                "token_format": getattr(k, "token_format", "legacy") or "legacy",
                "token_env": getattr(k, "token_env", "legacy") or "legacy",
                "workspace_id": k.workspace_id,
                "workspace_slug": ws.slug if ws else None,
                "created_at": k.created_at.isoformat() if k.created_at else "",
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
        )

    workspace_choices = [{"id": w.id, "slug": w.slug, "name": w.name} for w in workspaces]
    default_workspace_id = workspace_choices[0]["id"] if workspace_choices else 1

    return get_templates(request).TemplateResponse(
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


@router.get("/admin/api-keys/{name}", response_class=HTMLResponse)
async def admin_api_key_detail(request: Request, name: str) -> HTMLResponse:
    """Render the per-key management page.

    Shows metadata + grants editor (catalog + IP) + 30-day usage
    chart.  Grants and usage are loaded client-side via the JSON
    routes so the page itself stays a single template render.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.

    Returns:
        Rendered HTML response.

    Raises:
        CatalogNotFoundError: Key missing or revoked.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import ApiKey

    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(_select(ApiKey).where(ApiKey.name == name))
        if row is None:
            raise CatalogNotFoundError(f"api_key {name!r} not found")
        session.expunge(row)

    key_view = {
        "name": row.name,
        "secret_prefix": row.secret_prefix,
        "token_format": getattr(row, "token_format", "legacy") or "legacy",
        "token_env": getattr(row, "token_env", "legacy") or "legacy",
        "supervisor": bool(row.supervisor),
        "auditor": bool(row.auditor),
        "lineage_inbound": bool(getattr(row, "lineage_inbound", False)),
        "analyst": bool(getattr(row, "analyst", False)),
        "sql_execute": bool(getattr(row, "sql_execute", False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "expires_at": row.expires_at.isoformat() if getattr(row, "expires_at", None) else None,
        "quarantined_at": (
            row.quarantined_at.isoformat() if getattr(row, "quarantined_at", None) else None
        ),
        "quarantine_reason": getattr(row, "quarantine_reason", None),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_api_key_detail.html",
        {
            "key": key_view,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
