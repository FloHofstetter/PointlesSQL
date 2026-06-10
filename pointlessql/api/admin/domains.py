"""Admin CRUD for domains + their owner/developer members.

Tenant-admin-gated JSON endpoints plus one HTML cockpit page,
mirroring the workspace admin surface:

* ``GET  /admin/domains`` — HTML list + create form + per-row
  member drill-down.
* ``GET  /api/admin/domains`` — list domains in the active workspace.
* ``POST /api/admin/domains`` — create.
* ``PATCH /api/admin/domains/{id}`` — rename / edit description /
  change archetype.
* ``POST /api/admin/domains/{id}/archive`` — soft-archive.
* ``GET  /api/admin/domains/{id}/members`` — list members.
* ``POST /api/admin/domains/{id}/members`` — add (owner|developer).
* ``PATCH /api/admin/domains/{id}/members/{user_id}`` — change role.
* ``DELETE /api/admin/domains/{id}/members/{user_id}`` — remove.

Every mutation logs to :class:`AuditLog` via
:func:`pointlessql.api._audit_helpers.audit` with the ``domain.*``
action prefix so the admin cockpit + audit-of-audit pipeline pick
the events up without further wiring.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_user,
    require_admin,
)
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import (
    DOMAIN_ARCHETYPES,
    DOMAIN_MEMBER_ROLES,
    Domain,
    DomainMember,
    User,
)
from pointlessql.services import domains as domains_service

router = APIRouter(tags=["admin-domains"])


def _serialize_domain(row: Domain) -> dict[str, Any]:
    """Project a :class:`Domain` ORM row to a JSON-safe dict."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "archetype": row.archetype,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def _serialize_member(row: DomainMember, user_email: str | None = None) -> dict[str, Any]:
    """Project a :class:`DomainMember` row + the joined user email."""
    return {
        "id": row.id,
        "domain_id": row.domain_id,
        "user_id": row.user_id,
        "user_email": user_email,
        "role": row.role,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_domain(factory: Any, workspace_id: int, domain_id: int) -> Domain:
    """Return the workspace's domain or raise :class:`CatalogNotFoundError`."""
    with factory() as session:
        row = session.get(Domain, domain_id)
        if row is None or row.workspace_id != workspace_id:
            raise CatalogNotFoundError(f"domain id={domain_id} not found")
        session.expunge(row)
    return row


# ---------------------------------------------------------------------------
# JSON CRUD — domains
# ---------------------------------------------------------------------------


@router.get("/api/admin/domains")
async def api_admin_list_domains(
    request: Request, include_archived: bool = False
) -> dict[str, Any]:
    """List the active workspace's domains.

    Args:
        request: Incoming FastAPI request.
        include_archived: When ``True`` archived domains are included.

    Returns:
        ``{"domains": [...]}`` ordered by name ascending.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = domains_service.list_domains(
        factory, workspace_id=workspace_id, include_archived=include_archived
    )
    return {"domains": [_serialize_domain(row) for row in rows]}


@router.post("/api/admin/domains")
async def api_admin_create_domain(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a domain + an owner membership for the caller.

    Args:
        request: Incoming FastAPI request.
        body: ``{"slug": str, "name": str, "archetype": str,
            "description"?: str}``.

    Returns:
        The serialized domain row.

    Raises:
        ValidationError: On malformed slug / name / archetype or a
            slug already taken in the workspace.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    slug_raw = body.get("slug")
    name_raw = body.get("name")
    archetype_raw = body.get("archetype")
    if not isinstance(slug_raw, str) or not slug_raw.strip():
        raise ValidationError("slug must be a non-empty string")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ValidationError("name must be a non-empty string")
    if not isinstance(archetype_raw, str) or not archetype_raw.strip():
        raise ValidationError("archetype must be a non-empty string")
    description = body.get("description")
    user = get_user(request)
    creator_id = int(user["id"]) if user["id"] > 0 else None
    try:
        row = domains_service.create_domain(
            factory,
            workspace_id=workspace_id,
            slug=slug_raw,
            name=name_raw,
            archetype=archetype_raw.strip(),
            description=description if isinstance(description, str) else None,
            creator_user_id=creator_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "domain.created",
        f"domain:{row.slug}",
        {"id": row.id, "slug": row.slug, "name": row.name, "archetype": row.archetype},
    )
    return _serialize_domain(row)


@router.patch("/api/admin/domains/{domain_id}")
async def api_admin_update_domain(
    request: Request,
    domain_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Rename a domain, edit its description, or change its archetype.

    Args:
        request: Incoming FastAPI request.
        domain_id: ``Domain.id``.
        body: ``{"name"?: str, "description"?: str | None,
            "archetype"?: str}``.  At least one field required; slug
            is intentionally immutable (audit + URLs reference it).

    Returns:
        The updated domain row.

    Raises:
        ValidationError: When the body is empty or a field is invalid.
        CatalogNotFoundError: When no domain has that id.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)

    name = body.get("name")
    description_present = "description" in body
    description = body.get("description")
    archetype = body.get("archetype")

    if name is None and not description_present and archetype is None:
        raise ValidationError("at least one of name / description / archetype required")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
        raise ValidationError("name must be a non-empty string up to 200 chars")
    if description_present and description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string or null")
    if archetype is not None and (
        not isinstance(archetype, str) or archetype not in DOMAIN_ARCHETYPES
    ):
        raise ValidationError(f"archetype must be one of {sorted(DOMAIN_ARCHETYPES)}")

    with factory() as session:
        row = session.get(Domain, domain_id)
        assert row is not None  # _ensure_domain already validated
        if name is not None:
            row.name = name.strip()
        if description_present:
            stripped = description.strip() if isinstance(description, str) else ""
            row.description = stripped or None
        if archetype is not None:
            row.archetype = archetype
        session.commit()
        session.refresh(row)
        session.expunge(row)

    await audit(
        request,
        "domain.updated",
        f"domain:{row.slug}",
        {"id": row.id, "name": row.name, "archetype": row.archetype},
    )
    return _serialize_domain(row)


@router.post("/api/admin/domains/{domain_id}/archive")
async def api_admin_archive_domain(request: Request, domain_id: int) -> dict[str, Any]:
    """Soft-archive *domain_id*.

    Archiving leaves any product ``domain_id`` references intact — the
    products simply point at an archived domain, which the browse UI
    hides from the active list.

    Args:
        request: Incoming FastAPI request.
        domain_id: ``Domain.id`` to archive.

    Returns:
        The archived domain row.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)

    with factory() as session:
        row = session.get(Domain, domain_id)
        assert row is not None
        if row.archived_at is None:
            row.archived_at = datetime.datetime.now(datetime.UTC)
            session.commit()
            session.refresh(row)
        session.expunge(row)

    await audit(request, "domain.archived", f"domain:{row.slug}", {"id": row.id, "slug": row.slug})
    return _serialize_domain(row)


# ---------------------------------------------------------------------------
# JSON CRUD — members
# ---------------------------------------------------------------------------


@router.get("/api/admin/domains/{domain_id}/members")
async def api_admin_list_members(request: Request, domain_id: int) -> dict[str, Any]:
    """Return every member of *domain_id* with their joined email."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)
    with factory() as session:
        rows = list(
            session.execute(
                select(DomainMember, User.email)
                .join(User, User.id == DomainMember.user_id)
                .where(DomainMember.domain_id == domain_id)
                .order_by(DomainMember.role.asc(), User.email.asc())
            ).all()
        )
    members = [_serialize_member(member, user_email=email) for member, email in rows]
    return {"domain_id": domain_id, "members": members}


@router.post("/api/admin/domains/{domain_id}/members")
async def api_admin_add_member(
    request: Request,
    domain_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add (or update the role of) one member to a domain.

    Idempotent: re-adding a user with a different role updates the
    existing row in place.

    Args:
        request: Incoming FastAPI request.
        domain_id: Target domain.
        body: ``{"user_id"?: int, "user_email"?: str, "role"?: str}``.
            One of ``user_id`` / ``user_email`` is required; ``role``
            defaults to ``"owner"``.

    Returns:
        Serialized member row.

    Raises:
        ValidationError: When the body is malformed.
        CatalogNotFoundError: When the domain or user does not exist.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)

    user_id_raw = body.get("user_id")
    user_email_raw = body.get("user_email")
    role = (body.get("role") or "owner").strip().lower()
    if role not in DOMAIN_MEMBER_ROLES:
        raise ValidationError(f"role must be one of {sorted(DOMAIN_MEMBER_ROLES)}")

    target_user_id: int | None = None
    target_email: str | None = None
    with factory() as session:
        if isinstance(user_id_raw, int):
            user = session.get(User, user_id_raw)
            if user is None:
                raise CatalogNotFoundError(f"user id={user_id_raw} not found")
            target_user_id = user.id
            target_email = user.email
        elif isinstance(user_email_raw, str) and user_email_raw.strip():
            user = session.scalar(select(User).where(User.email == user_email_raw.strip().lower()))
            if user is None:
                raise CatalogNotFoundError(f"user email={user_email_raw!r} not found")
            target_user_id = user.id
            target_email = user.email
        else:
            raise ValidationError("user_id or user_email is required")

    assert target_user_id is not None
    member = domains_service.add_member(
        factory, domain_id=domain_id, user_id=target_user_id, role=role
    )
    await audit(
        request,
        "domain.member_added",
        f"domain:{domain_id}",
        {"user_id": target_user_id, "user_email": target_email, "role": role},
    )
    return _serialize_member(member, user_email=target_email)


@router.patch("/api/admin/domains/{domain_id}/members/{user_id}")
async def api_admin_update_member_role(
    request: Request,
    domain_id: int,
    user_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Change a member's role.

    Args:
        request: Incoming FastAPI request.
        domain_id: ``Domain.id``.
        user_id: ``User.id``.
        body: ``{"role": "owner" | "developer"}``.

    Returns:
        Updated member row.

    Raises:
        CatalogNotFoundError: When the membership does not exist.
        ValidationError: When the role is invalid.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)

    role = (body.get("role") or "").strip().lower()
    if role not in DOMAIN_MEMBER_ROLES:
        raise ValidationError(f"role must be one of {sorted(DOMAIN_MEMBER_ROLES)}")

    with factory() as session:
        member = session.scalar(
            select(DomainMember).where(
                DomainMember.domain_id == domain_id,
                DomainMember.user_id == user_id,
            )
        )
        if member is None:
            raise CatalogNotFoundError(
                f"user_id={user_id} is not a member of domain_id={domain_id}"
            )
        member.role = role
        session.commit()
        session.refresh(member)
        session.expunge(member)

    await audit(
        request,
        "domain.member_role_changed",
        f"domain:{domain_id}",
        {"user_id": user_id, "role": role},
    )
    return _serialize_member(member)


@router.delete("/api/admin/domains/{domain_id}/members/{user_id}")
async def api_admin_remove_member(request: Request, domain_id: int, user_id: int) -> dict[str, Any]:
    """Remove a user from a domain.

    Returns:
        ``{"deleted": bool}`` — ``False`` when no membership existed.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    _ensure_domain(factory, workspace_id, domain_id)

    deleted = domains_service.remove_member(factory, domain_id=domain_id, user_id=user_id)
    if deleted:
        await audit(
            request,
            "domain.member_removed",
            f"domain:{domain_id}",
            {"user_id": user_id},
        )
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------


@router.get("/admin/domains", response_class=HTMLResponse)
async def admin_domains_page(request: Request):
    """Render the admin domains cockpit.

    Combines the list view, create form, and per-row member
    drill-down into one HTMX-driven page so admins manage the most
    common flows without route hopping.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    active = domains_service.list_domains(
        factory, workspace_id=workspace_id, include_archived=False
    )
    all_rows = domains_service.list_domains(
        factory, workspace_id=workspace_id, include_archived=True
    )
    archived = [r for r in all_rows if r.archived_at is not None]
    member_counts: dict[int, int] = {}
    product_counts: dict[int, int] = {}
    for row in all_rows:
        member_counts[row.id] = len(domains_service.list_members(factory, domain_id=row.id))
        product_counts[row.id] = len(
            domains_service.list_products_for_domain(factory, domain_id=row.id)
        )

    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_domains.html",
        {
            "active_page": "admin",
            "active_domains": active,
            "archived_domains": archived,
            "member_counts": member_counts,
            "product_counts": product_counts,
        },
    )
