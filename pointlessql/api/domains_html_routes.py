"""Domain browse surface — read-only pages + JSON for all users.

Domains are *managed* by admins (see :mod:`pointlessql.api.admin.domains`)
but *browsable* by every authenticated user, mirroring the
data-product split:

* ``GET /domains`` — index with a card per active domain.
* ``GET /domains/{slug}`` — detail page (members + owned products).
* ``GET /api/domains`` — JSON list (active by default) used by the
  browse page and the ``pql_list_domains`` agent tool.
* ``GET /api/domains/{slug}`` — JSON detail (domain + members +
  owned products).

The HTML pages redirect anonymous visitors to ``/auth/login?next=...``
so the deep-link survives the OIDC round-trip; the auth middleware
already gates everything outside ``PUBLIC_PREFIXES`` so no allowlist
entry is needed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_user,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DomainMember, User
from pointlessql.services import domains as domains_service

router = APIRouter(tags=["domains"])


def _serialise_domain(row: Any) -> dict[str, Any]:
    """Render a :class:`Domain` row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "archetype": row.archetype,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def _members_with_email(factory: Any, domain_id: int) -> list[dict[str, Any]]:
    """Return the domain's members joined to their user email."""
    with factory() as session:
        rows = list(
            session.execute(
                select(DomainMember, User.email, User.display_name)
                .join(User, User.id == DomainMember.user_id)
                .where(DomainMember.domain_id == domain_id)
                .order_by(DomainMember.role.asc(), User.email.asc())
            ).all()
        )
    return [
        {
            "user_id": member.user_id,
            "role": member.role,
            "email": email,
            "display_name": display_name,
        }
        for member, email, display_name in rows
    ]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


@router.get("/api/domains")
async def api_list_domains(request: Request, include_archived: bool = False) -> dict[str, Any]:
    """List the active workspace's domains with owner + product counts."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = domains_service.list_domains(
        factory, workspace_id=workspace_id, include_archived=include_archived
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        members = _members_with_email(factory, row.id)
        owners = [m for m in members if m["role"] == "owner"]
        product_count = len(
            domains_service.list_products_for_domain(factory, domain_id=row.id)
        )
        payload = _serialise_domain(row)
        payload["owners"] = owners
        payload["member_count"] = len(members)
        payload["product_count"] = product_count
        out.append(payload)
    return {"domains": out}


@router.get("/api/domains/{slug}")
async def api_domain_detail(request: Request, slug: str) -> dict[str, Any]:
    """Return one domain with its members + owned products."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    domain = domains_service.get_domain_by_slug(factory, workspace_id=workspace_id, slug=slug)
    if domain is None:
        raise ResourceNotFoundError(f"domain {slug!r} not found")
    products = domains_service.list_products_for_domain(factory, domain_id=domain.id)
    payload = _serialise_domain(domain)
    payload["members"] = _members_with_email(factory, domain.id)
    payload["products"] = [
        {
            "id": p.id,
            "catalog": p.catalog_name,
            "schema": p.schema_name,
            "ref": f"{p.catalog_name}.{p.schema_name}",
            "version": p.version,
            "description": p.description,
        }
        for p in products
    ]
    return payload


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@router.get("/domains", response_class=HTMLResponse, response_model=None)
async def domains_index_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the workspace-wide domain index page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/domains", status_code=303)
    return get_templates(request).TemplateResponse(
        request,
        "pages/domains.html",
        {"active_page": "domains", "is_admin": user["is_admin"]},
    )


@router.get("/domains/{slug}", response_class=HTMLResponse, response_model=None)
async def domain_detail_page(request: Request, slug: str) -> HTMLResponse | RedirectResponse:
    """Render one domain's detail page (members + owned products)."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url=f"/auth/login?next=/domains/{slug}", status_code=303)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    domain = domains_service.get_domain_by_slug(factory, workspace_id=workspace_id, slug=slug)
    if domain is None:
        raise ResourceNotFoundError(f"domain {slug!r} not found")
    return get_templates(request).TemplateResponse(
        request,
        "pages/domain_detail.html",
        {
            "active_page": "domains",
            "is_admin": user["is_admin"],
            "domain_slug": domain.slug,
            "domain_name": domain.name,
        },
    )
