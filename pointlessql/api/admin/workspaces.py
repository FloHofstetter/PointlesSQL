"""Admin CRUD for workspaces, members, and the soft-archive flow.

Six tenant-admin-gated JSON endpoints + one HTML cockpit page:

* ``GET  /admin/workspaces`` — HTML list + create form + per-row
  drill-down (members, pins, archive).
* ``GET  /api/admin/workspaces`` — list active workspaces.
* ``POST /api/admin/workspaces`` — create.
* ``PATCH /api/admin/workspaces/{id}`` — rename / edit description.
* ``POST /api/admin/workspaces/{id}/archive`` — soft-archive
  (sets ``archived_at``).
* ``POST /api/admin/workspaces/{id}/members`` — add a member.
* ``PATCH /api/admin/workspaces/{id}/members/{user_id}`` — change role.
* ``DELETE /api/admin/workspaces/{id}/members/{user_id}`` — remove.

Every mutation logs to :class:`AuditLog` via
:func:`pointlessql.api._audit_helpers.audit` with action prefix
``workspace.*`` so the admin cockpit + audit-of-audit pipeline pick
the events up without further wiring.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import (
    WORKSPACE_ROLES,
    User,
    Workspace,
    WorkspaceCatalogPin,
    WorkspaceMember,
)
from pointlessql.services.workspace import _crud as workspaces_service

router = APIRouter(tags=["admin-workspaces"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def _serialize_workspace(row: Workspace) -> dict[str, Any]:
    """Project a :class:`Workspace` ORM row to a JSON-safe dict."""
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def _serialize_member(row: WorkspaceMember, user_email: str | None = None) -> dict[str, Any]:
    """Project a :class:`WorkspaceMember` row + the joined user email."""
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "user_id": row.user_id,
        "user_email": user_email,
        "role": row.role,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_workspace(factory: Any, workspace_id: int) -> Workspace:
    """Return the workspace or raise :class:`CatalogNotFoundError`."""
    with factory() as session:
        ws = session.get(Workspace, workspace_id)
        if ws is None:
            raise CatalogNotFoundError(f"workspace id={workspace_id} not found")
        session.expunge(ws)
    return ws


# ---------------------------------------------------------------------------
# JSON CRUD — workspaces
# ---------------------------------------------------------------------------


@router.get("/api/admin/workspaces")
async def api_admin_list_workspaces(
    request: Request, include_archived: bool = False
) -> dict[str, Any]:
    """List workspaces with optional archived inclusion.

    Args:
        request: Incoming FastAPI request.
        include_archived: When ``True`` archived workspaces are
            included in the response.

    Returns:
        ``{"workspaces": [...]}`` ordered by ``name`` ascending.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(Workspace)
        if not include_archived:
            stmt = stmt.where(Workspace.archived_at.is_(None))
        rows = list(session.scalars(stmt.order_by(Workspace.name.asc())).all())
        for row in rows:
            session.expunge(row)
    return {"workspaces": [_serialize_workspace(row) for row in rows]}


@router.post("/api/admin/workspaces")
async def api_admin_create_workspace(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new workspace and admin-membership for the caller.

    Args:
        request: Incoming FastAPI request.
        body: ``{"slug": str, "name": str, "description"?: str}``.

    Returns:
        Serialized workspace row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin.

    Raises:
        ValidationError: When the slug is malformed or already
            exists, or the name is missing / too long.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    slug_raw = body.get("slug")
    name_raw = body.get("name")
    if not isinstance(slug_raw, str) or not slug_raw.strip():
        raise ValidationError("slug must be a non-empty string")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ValidationError("name must be a non-empty string")
    description = body.get("description")
    user = getattr(request.state, "user", None)
    creator_id: int | None = None
    if user and isinstance(user.get("id"), int) and user["id"] > 0:
        creator_id = int(user["id"])
    try:
        row = workspaces_service.create_workspace(
            factory,
            slug=slug_raw,
            name=name_raw,
            description=description if isinstance(description, str) else None,
            creator_user_id=creator_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "workspace.created",
        f"workspace:{row.slug}",
        {"id": row.id, "slug": row.slug, "name": row.name},
    )
    return _serialize_workspace(row)


@router.patch("/api/admin/workspaces/{workspace_id}")
async def api_admin_update_workspace(
    request: Request,
    workspace_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Rename a workspace or update its description.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id``.
        body: ``{"name"?: str, "description"?: str | None}``.  At
            least one field required; slug is intentionally
            immutable (audit rows reference it).

    Returns:
        The updated workspace row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin; ``_ensure_workspace`` raises
    ``CatalogNotFoundError`` when no workspace has that id.

    Raises:
        ValidationError: When the body is empty or a name is
            longer than 200 chars.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    name = body.get("name")
    description_field_present = "description" in body
    description = body.get("description")

    if name is None and not description_field_present:
        raise ValidationError("at least one of name / description required")
    if name is not None:
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValidationError("name must be a non-empty string up to 200 chars")
    if description_field_present and description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string or null")

    with factory() as session:
        row = session.get(Workspace, workspace_id)
        assert row is not None  # _ensure_workspace already validated
        if name is not None:
            row.name = name.strip()
        if description_field_present:
            stripped = description.strip() if isinstance(description, str) else ""
            row.description = stripped or None
        session.commit()
        session.refresh(row)
        session.expunge(row)

    await audit(
        request,
        "workspace.updated",
        f"workspace:{row.slug}",
        {"id": row.id, "name": row.name, "description": row.description},
    )
    return _serialize_workspace(row)


@router.post("/api/admin/workspaces/{workspace_id}/archive")
async def api_admin_archive_workspace(request: Request, workspace_id: int) -> dict[str, Any]:
    """Soft-archive *workspace_id*.

    Refuses to archive the seeded ``default`` workspace (id=1) — the
    fallback resolver depends on it always being live.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id`` to archive.

    Returns:
        The archived workspace row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin; ``_ensure_workspace`` raises
    ``CatalogNotFoundError`` when the workspace does not exist.

    Raises:
        ValidationError: When asked to archive id=1.
    """
    require_admin(request)
    if workspace_id == workspaces_service.DEFAULT_WORKSPACE_ID:
        raise ValidationError("the default workspace cannot be archived")
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    with factory() as session:
        row = session.get(Workspace, workspace_id)
        assert row is not None
        if row.archived_at is None:
            row.archived_at = datetime.datetime.now(datetime.UTC)
            session.commit()
            session.refresh(row)
        session.expunge(row)

    await audit(
        request,
        "workspace.archived",
        f"workspace:{row.slug}",
        {"id": row.id, "slug": row.slug},
    )
    return _serialize_workspace(row)


# ---------------------------------------------------------------------------
# JSON CRUD — members
# ---------------------------------------------------------------------------


@router.get("/api/admin/workspaces/{workspace_id}/members")
async def api_admin_list_members(request: Request, workspace_id: int) -> dict[str, Any]:
    """Return every member of *workspace_id* with their joined email."""
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)
    with factory() as session:
        rows = list(
            session.execute(
                select(WorkspaceMember, User.email)
                .join(User, User.id == WorkspaceMember.user_id)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(User.email.asc())
            ).all()
        )
    members = [_serialize_member(member, user_email=email) for member, email in rows]
    return {"workspace_id": workspace_id, "members": members}


@router.post("/api/admin/workspaces/{workspace_id}/members")
async def api_admin_add_member(
    request: Request,
    workspace_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add (or update the role of) one member to a workspace.

    Idempotent at the API level — re-adding a user with a different
    role updates the existing row in place rather than 409ing.

    Args:
        request: Incoming FastAPI request.
        workspace_id: Target workspace.
        body: ``{"user_id"?: int, "user_email"?: str, "role"?: str}``.
            One of ``user_id`` / ``user_email`` is required; ``role``
            defaults to ``"member"``.

    Returns:
        Serialized member row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin.

    Raises:
        ValidationError: When the body is malformed.
        CatalogNotFoundError: When the workspace or user does not
            exist.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    user_id_raw = body.get("user_id")
    user_email_raw = body.get("user_email")
    role = (body.get("role") or "member").strip().lower()
    if role not in WORKSPACE_ROLES:
        raise ValidationError(f"role must be one of {sorted(WORKSPACE_ROLES)}")

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

    assert target_user_id is not None  # narrowed by raises above
    member = workspaces_service.add_member(
        factory,
        workspace_id=workspace_id,
        user_id=target_user_id,
        role=role,
    )
    await audit(
        request,
        "workspace.member_added",
        f"workspace:{workspace_id}",
        {"user_id": target_user_id, "user_email": target_email, "role": role},
    )
    return _serialize_member(member, user_email=target_email)


@router.patch("/api/admin/workspaces/{workspace_id}/members/{user_id}")
async def api_admin_update_member_role(
    request: Request,
    workspace_id: int,
    user_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Change a member's role.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id``.
        user_id: ``User.id``.
        body: ``{"role": "admin" | "member"}``.

    Returns:
        Updated member row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin.

    Raises:
        CatalogNotFoundError: When the membership does not exist.
        ValidationError: When the role is invalid.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    role = (body.get("role") or "").strip().lower()
    if role not in WORKSPACE_ROLES:
        raise ValidationError(f"role must be one of {sorted(WORKSPACE_ROLES)}")

    with factory() as session:
        member = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member is None:
            raise CatalogNotFoundError(
                f"user_id={user_id} is not a member of workspace_id={workspace_id}"
            )
        member.role = role
        session.commit()
        session.refresh(member)
        session.expunge(member)

    await audit(
        request,
        "workspace.member_role_changed",
        f"workspace:{workspace_id}",
        {"user_id": user_id, "role": role},
    )
    return _serialize_member(member)


@router.delete("/api/admin/workspaces/{workspace_id}/members/{user_id}")
async def api_admin_remove_member(
    request: Request, workspace_id: int, user_id: int
) -> dict[str, Any]:
    """Remove a user from a workspace.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id``.
        user_id: ``User.id``.

    Returns:
        ``{"deleted": bool}`` — ``False`` when no membership existed.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    deleted = False
    with factory() as session:
        member = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if member is not None:
            session.delete(member)
            session.commit()
            deleted = True

    if deleted:
        await audit(
            request,
            "workspace.member_removed",
            f"workspace:{workspace_id}",
            {"user_id": user_id},
        )
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------


@router.get("/admin/workspaces", response_class=HTMLResponse)
async def admin_workspaces_page(request: Request):
    """Render the admin workspaces cockpit.

    Combines the list view, create form, and per-row drill-down
    (members + pins) into one HTMX-driven page so admins don't have
    to navigate between separate routes for the most common flows.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        active = list(
            session.scalars(
                select(Workspace)
                .where(Workspace.archived_at.is_(None))
                .order_by(Workspace.name.asc())
            ).all()
        )
        archived = list(
            session.scalars(
                select(Workspace)
                .where(Workspace.archived_at.is_not(None))
                .order_by(Workspace.archived_at.desc())
            ).all()
        )
        pin_counts: dict[int, int] = {}
        member_counts: dict[int, int] = {}
        for ws in active + archived:
            pin_counts[ws.id] = (
                session.scalar(
                    select(WorkspaceCatalogPin.id)
                    .where(WorkspaceCatalogPin.workspace_id == ws.id)
                    .order_by(WorkspaceCatalogPin.id)
                    .limit(1)
                )
                or 0
            )
            member_counts[ws.id] = len(
                list(
                    session.scalars(
                        select(WorkspaceMember.id).where(WorkspaceMember.workspace_id == ws.id)
                    ).all()
                )
            )
        for ws in active + archived:
            session.expunge(ws)

    return _templates(request).TemplateResponse(
        request,
        "pages/admin_workspaces.html",
        {
            "active_page": "admin",
            "active_workspaces": active,
            "archived_workspaces": archived,
            "member_counts": member_counts,
            "pin_counts": pin_counts,
        },
    )
