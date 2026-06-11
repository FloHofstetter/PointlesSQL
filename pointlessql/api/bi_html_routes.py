"""HTML pages for the AI/BI widget dashboards.

The JSON surface lives in :mod:`pointlessql.api.bi_dashboards_routes`;
this module only renders the list / view / editor pages plus the
unauthenticated public viewer.  Widget data always flows through the
JSON endpoints, so every page here is a thin server-rendered shell the
``biDashboard*`` Alpine factories hydrate client-side.

The public viewer reuses the same grid partial as the authenticated
view but renders it inside the chromeless ``base_public.html`` layout
(the notebook-share pattern): the token in the URL is the credential,
and the page wires its widget-data calls to ``/api/bi/public/…``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from pointlessql.api.bi_dashboards_routes._shared import (
    ensure_can_edit,
    ensure_dashboard,
    serialize_dashboard,
    serialize_widget,
)
from pointlessql.api.dependencies import current_workspace_id, get_templates, get_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.services import bi_dashboards as bi_service

router = APIRouter(tags=["bi-dashboards-html"])


def _owner_emails(request: Request, owner_ids: set[int]) -> dict[int, str]:
    """Map owner ids to e-mails for display on the list page.

    Resolved here (not in the serializer) because only the HTML list
    page shows owners — the JSON surface keeps the raw ``owner_id``
    so API consumers join against ``/api/admin/users`` themselves.

    Args:
        request: Incoming FastAPI request (for the session factory).
        owner_ids: Distinct ``owner_id`` values to resolve.

    Returns:
        ``owner_id → email`` for every id that still has a user row.
    """
    if not owner_ids:
        return {}
    factory = request.app.state.session_factory
    with factory() as session:
        rows = session.scalars(select(User).where(User.id.in_(owner_ids)))
        return {row.id: row.email for row in rows}


def _serialized_widgets(request: Request, dashboard_id: int) -> list[dict[str, Any]]:
    """Return a dashboard's widgets in the JSON-API shape.

    The templates inline this list into the page factory's config via
    ``|tojson``, so the shape must match what the JSON endpoints
    return — hence the shared serializer instead of raw ORM rows.
    """
    factory = request.app.state.session_factory
    widgets = bi_service.list_widgets(factory, dashboard_id=dashboard_id)
    return [serialize_widget(w) for w in widgets]


def _can_edit(request: Request, owner_id: int) -> bool:
    """Return whether the current user may mutate the dashboard."""
    user = get_user(request)
    return bool(user["is_admin"]) or int(user["id"]) == owner_id


@router.get("/bi/public/{token}", response_class=HTMLResponse)
async def bi_dashboard_public_page(request: Request, token: str) -> HTMLResponse:
    """Render a published dashboard for anonymous viewers.

    Declared before the ``/bi/{slug}`` routes so ``public`` can never
    be captured as a slug.  The token is the credential (mirroring the
    notebook ``/share/`` viewer); widget queries run as the owner via
    the ``/api/bi/public/{token}`` data path the page wires itself to.

    Args:
        request: Incoming FastAPI request.
        token: Public-share token from the URL.

    Returns:
        The rendered chromeless viewer page.

    Raises:
        ResourceNotFoundError: For unknown or revoked tokens.
    """
    factory = request.app.state.session_factory
    dashboard = bi_service.get_dashboard_by_token(factory, token=token)
    if dashboard is None:
        raise ResourceNotFoundError("Published dashboard not found.")
    return get_templates(request).TemplateResponse(
        request,
        "pages/bi_dashboard_public.html",
        {
            "dashboard": serialize_dashboard(dashboard),
            "widgets": _serialized_widgets(request, dashboard.id),
            "public_token": token,
        },
    )


@router.get("/bi", response_class=HTMLResponse)
async def bi_dashboards_page(request: Request) -> HTMLResponse:
    """Render the dashboards list page (any logged-in user)."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    pairs = bi_service.list_dashboards(factory, workspace_id=workspace_id)
    dashboards = [serialize_dashboard(row, widget_count=count) for row, count in pairs]
    owners = _owner_emails(request, {d["owner_id"] for d in dashboards})
    return get_templates(request).TemplateResponse(
        request,
        "pages/bi_dashboards.html",
        {
            "active_page": "bi",
            "dashboards": dashboards,
            "owners": owners,
        },
    )


@router.get("/bi/{slug}", response_class=HTMLResponse)
async def bi_dashboard_view_page(request: Request, slug: str) -> HTMLResponse:
    """Render one dashboard's read-only grid (any logged-in user).

    Edit / publish affordances render only for the owner and admins;
    the JSON mutations re-check the same permission server-side.
    """
    row = ensure_dashboard(request, slug)
    return get_templates(request).TemplateResponse(
        request,
        "pages/bi_dashboard_view.html",
        {
            "active_page": "bi",
            "dashboard": serialize_dashboard(row),
            "widgets": _serialized_widgets(request, row.id),
            "can_edit": _can_edit(request, row.owner_id),
        },
    )


@router.get("/bi/{slug}/edit", response_class=HTMLResponse)
async def bi_dashboard_edit_page(request: Request, slug: str) -> HTMLResponse:
    """Render the dashboard editor (owner or admin only).

    The permission gate runs here — not just in the JSON layer —
    because the editor page is useless chrome for a viewer who cannot
    save anything; a 403 with the role hint is the clearer answer.
    """
    row = ensure_dashboard(request, slug)
    ensure_can_edit(request, row)
    return get_templates(request).TemplateResponse(
        request,
        "pages/bi_dashboard_edit.html",
        {
            "active_page": "bi",
            "dashboard": serialize_dashboard(row),
            "widgets": _serialized_widgets(request, row.id),
        },
    )
