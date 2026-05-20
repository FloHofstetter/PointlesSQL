"""Per-notebook share permissions (Phase 99).

Layered on top of the workspace membership model: a workspace
member who has no explicit row in ``notebook_permissions`` still
falls back to the workspace role.  Rows here grant access *in
addition* to that — so a stakeholder with view-only on the
workspace can be elevated to "run" on a single notebook, or a
non-workspace-member can be given "view" outside the tenant
default.

Roles form a lattice ``view < run < edit``; a higher role
implicitly grants the lower ones.  :func:`role_satisfies` is the
single chokepoint the route layer uses to gate an action.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookPermission

VALID_ROLES: tuple[str, ...] = ("view", "run", "edit")
#: Role rank — higher number means more capabilities.
_ROLE_RANK: dict[str, int] = {"view": 1, "run": 2, "edit": 3}


def role_satisfies(have: str | None, need: str) -> bool:
    """Return ``True`` when ``have`` grants at least ``need``.

    Args:
        have: The actor's effective role (``None`` for no grant).
        need: The required role.

    Returns:
        ``True`` when ``_ROLE_RANK[have] >= _ROLE_RANK[need]``.
    """
    if have is None:
        return False
    return _ROLE_RANK.get(have, 0) >= _ROLE_RANK.get(need, 99)


def _check_role(role: str) -> None:
    """Reject role strings outside :data:`VALID_ROLES`."""
    if role not in VALID_ROLES:
        raise ValidationError(
            f"role must be one of {VALID_ROLES}; got {role!r}"
        )


def grant_permission(
    session: Session,
    *,
    notebook_id: str,
    user_id: int,
    role: str,
    granted_by_user_id: int | None,
) -> NotebookPermission:
    """Insert or replace one ``(notebook, user)`` grant.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        user_id: ``users.id`` of the grantee.
        role: One of :data:`VALID_ROLES`.
        granted_by_user_id: Audit pointer to the grantor.

    Returns:
        The (new or updated) row.

    Raises:
        ValidationError: When ``role`` is invalid or ``notebook_id``
            does not exist.
    """
    _check_role(role)
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    row = session.execute(
        select(NotebookPermission).where(
            NotebookPermission.notebook_id == notebook_id,
            NotebookPermission.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = NotebookPermission(
            notebook_id=notebook_id,
            user_id=user_id,
            role=role,
            granted_by_user_id=granted_by_user_id,
        )
        session.add(row)
    else:
        row.role = role
        row.granted_by_user_id = granted_by_user_id
    session.flush()
    return row


def revoke_permission(
    session: Session, *, notebook_id: str, user_id: int
) -> bool:
    """Delete one ``(notebook, user)`` grant; idempotent.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        user_id: ``users.id`` of the grantee.

    Returns:
        ``True`` when a row was removed; ``False`` when none matched.
    """
    row = session.execute(
        select(NotebookPermission).where(
            NotebookPermission.notebook_id == notebook_id,
            NotebookPermission.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def list_permissions(
    session: Session, *, notebook_id: str
) -> list[dict[str, Any]]:
    """Return every explicit grant on a notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        List of dicts ``{user_id, role, granted_at, granted_by_user_id}``.
    """
    rows = session.execute(
        select(NotebookPermission)
        .where(NotebookPermission.notebook_id == notebook_id)
        .order_by(NotebookPermission.granted_at.asc(), NotebookPermission.id.asc())
    ).scalars().all()
    return [
        {
            "user_id": r.user_id,
            "role": r.role,
            "granted_by_user_id": r.granted_by_user_id,
            "granted_at": r.granted_at.isoformat() if r.granted_at else None,
        }
        for r in rows
    ]


def get_effective_role(
    session: Session, *, notebook_id: str, user_id: int
) -> str | None:
    """Return the explicit role for one user on one notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        user_id: ``users.id``.

    Returns:
        The role string when a row exists; ``None`` otherwise.  The
        caller is responsible for layering this on top of the
        workspace-membership fallback.
    """
    row = session.execute(
        select(NotebookPermission).where(
            NotebookPermission.notebook_id == notebook_id,
            NotebookPermission.user_id == user_id,
        )
    ).scalar_one_or_none()
    return row.role if row is not None else None


__all__ = [
    "VALID_ROLES",
    "get_effective_role",
    "grant_permission",
    "list_permissions",
    "revoke_permission",
    "role_satisfies",
]
