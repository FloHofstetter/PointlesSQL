"""Admin cockpit page for workspace secret scopes.

One HTML route — the JSON surface lives in
:mod:`pointlessql.api.secrets_routes` and is shared with non-admin
users (ACL-gated).  The cockpit renders every scope of the active
workspace (admins hold implicit ``MANAGE``) with its key count, and
the page factory drives all mutations through ``/api/secrets``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.services import secret_scopes as scopes_service

router = APIRouter(tags=["admin-secrets"])


@router.get("/admin/secrets", response_class=HTMLResponse)
async def admin_secrets_page(request: Request):
    """Render the admin secrets cockpit (scopes + keys + ACLs)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    pairs = scopes_service.list_scopes(
        factory,
        workspace_id=workspace_id,
        principal=user["email"] if user["id"] > 0 else None,
        is_admin=True,
    )
    scopes = [scope for scope, _permission in pairs]
    key_counts: dict[int, int] = {
        scope.id: len(scopes_service.list_secret_keys(factory, scope_id=scope.id))
        for scope in scopes
    }
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_secrets.html",
        {
            "active_page": "admin",
            "scopes": scopes,
            "key_counts": key_counts,
        },
    )
