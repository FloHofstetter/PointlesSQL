"""CRUD helpers for ``audit_saved_filters`` — admin's named filter combos."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select

from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models import AuditSavedFilter

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _row_to_entry(row: AuditSavedFilter) -> dict[str, Any]:
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "name": row.name,
        "filters": _safe_parse_json(row.filters_json),
        "is_shared_workspace": bool(row.is_shared_workspace),
        "workspace_id": row.workspace_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _safe_parse_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def list_for_user(
    factory: sessionmaker[Session],
    *,
    user_id: int,
    workspace_id: int,
) -> list[dict[str, Any]]:
    """Return filters owned by *user_id* OR shared in *workspace_id*."""
    stmt = (
        select(AuditSavedFilter)
        .where(
            or_(
                AuditSavedFilter.owner_user_id == user_id,
                (
                    (AuditSavedFilter.is_shared_workspace.is_(True))
                    & (AuditSavedFilter.workspace_id == workspace_id)
                ),
            )
        )
        .order_by(AuditSavedFilter.created_at.desc())
    )
    with factory() as session:
        rows = list(session.scalars(stmt).all())
        return [_row_to_entry(r) for r in rows]


def create_filter(
    factory: sessionmaker[Session],
    *,
    owner_user_id: int,
    name: str,
    filters: dict[str, Any],
    is_shared_workspace: bool = False,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Insert a new saved filter; raise ``ValueError`` on duplicate name."""
    if not name.strip():
        raise ValueError("saved filter name cannot be empty")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(AuditSavedFilter)
            .where(AuditSavedFilter.owner_user_id == owner_user_id)
            .where(AuditSavedFilter.name == name.strip())
        )
        if existing is not None:
            raise ValueError(f"saved filter named {name.strip()!r} already exists")
        row = AuditSavedFilter(
            owner_user_id=owner_user_id,
            name=name.strip(),
            filters_json=json.dumps(filters, default=str),
            is_shared_workspace=bool(is_shared_workspace),
            workspace_id=workspace_id if is_shared_workspace else None,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _row_to_entry(row)


def update_filter(
    factory: sessionmaker[Session],
    *,
    filter_id: int,
    actor_user_id: int,
    name: str | None = None,
    filters: dict[str, Any] | None = None,
    is_shared_workspace: bool | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Update a saved filter — owner only."""
    with factory() as session:
        row = session.get(AuditSavedFilter, filter_id)
        if row is None:
            raise ResourceNotFoundError(f"saved filter id={filter_id} not found")
        if row.owner_user_id != actor_user_id:
            raise AuthorizationError(
                principal=str(actor_user_id),
                privilege="audit-saved-filter-edit",
                securable_type="audit_saved_filter",
                full_name=str(filter_id),
            )
        if name is not None:
            row.name = name.strip()
        if filters is not None:
            row.filters_json = json.dumps(filters, default=str)
        if is_shared_workspace is not None:
            row.is_shared_workspace = bool(is_shared_workspace)
            if not is_shared_workspace:
                row.workspace_id = None
        if workspace_id is not None and (is_shared_workspace or row.is_shared_workspace):
            row.workspace_id = workspace_id
        session.commit()
        session.refresh(row)
        return _row_to_entry(row)


def delete_filter(
    factory: sessionmaker[Session],
    *,
    filter_id: int,
    actor_user_id: int,
) -> None:
    """Delete a saved filter — owner only."""
    with factory() as session:
        row = session.get(AuditSavedFilter, filter_id)
        if row is None:
            raise ResourceNotFoundError(f"saved filter id={filter_id} not found")
        if row.owner_user_id != actor_user_id:
            raise AuthorizationError(
                principal=str(actor_user_id),
                privilege="audit-saved-filter-delete",
                securable_type="audit_saved_filter",
                full_name=str(filter_id),
            )
        session.delete(row)
        session.commit()


__all__ = [
    "create_filter",
    "delete_filter",
    "list_for_user",
    "update_filter",
]
