"""``GET /admin/review-destinations`` — webhook destinations for review events."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_admin

router = APIRouter(tags=["admin"])


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
    from pointlessql.models.agent._reviews import REVIEW_SEVERITIES, ReviewDestination

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

    return get_templates(request).TemplateResponse(
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
