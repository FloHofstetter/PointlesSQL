"""App Spaces — governance grouping over hosted apps.

An App Space groups several hosted apps and declares their shared API
scopes (for on-behalf-of-user access) once, instead of per app.  This
module is the registry: CRUD on spaces, assigning an app to a space, and
resolving an app's *effective* scopes (the scopes of its space).  The
actual on-behalf-of-user enforcement is layered by the grant / policy
stack on top of these declarations.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import AppSpace, HostedApp


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _clean_scopes(scopes: list[str] | None) -> list[str]:
    """Normalise an API-scope list (trimmed, de-duplicated, ordered)."""
    seen: dict[str, None] = {}
    for scope in scopes or []:
        token = str(scope).strip()
        if token:
            seen.setdefault(token, None)
    return list(seen)


def _parse_scopes(raw: str | None) -> list[str]:
    """Decode a space's stored ``api_scopes`` JSON into a list."""
    if not raw:
        return []
    try:
        parsed: Any = json.loads(raw)
    except TypeError, ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in cast("list[Any]", parsed)]


def _serialize(space: AppSpace, *, app_count: int) -> dict[str, Any]:
    """Render a space row + its member-app count into a JSON-safe dict."""
    return {
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "api_scopes": _parse_scopes(space.api_scopes),
        "app_count": app_count,
        "created_by": space.created_by,
    }


def _app_counts(session: Session, workspace_id: int) -> dict[int, int]:
    """Count member apps per space for a workspace."""
    counts: dict[int, int] = {}
    rows = session.scalars(
        select(HostedApp).where(
            HostedApp.workspace_id == workspace_id,
            HostedApp.app_space_id.is_not(None),
        )
    ).all()
    for row in rows:
        if row.app_space_id is not None:
            counts[row.app_space_id] = counts.get(row.app_space_id, 0) + 1
    return counts


def list_spaces(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """List a workspace's app spaces with member-app counts.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.

    Returns:
        Serialized space dicts ordered by name.
    """
    with factory() as session:
        spaces = list(
            session.scalars(
                select(AppSpace)
                .where(AppSpace.workspace_id == workspace_id)
                .order_by(AppSpace.name)
            ).all()
        )
        counts = _app_counts(session, workspace_id)
        return [_serialize(space, app_count=counts.get(space.id, 0)) for space in spaces]


def create_space(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: str,
    description: str | None = None,
    api_scopes: list[str] | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Create an app space.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.
        name: Space name, unique per workspace.
        description: Optional rationale.
        api_scopes: API scopes the space's apps may use.
        created_by: Authoring principal.

    Returns:
        The serialized new space.

    Raises:
        ValidationError: When the name is empty or already taken.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("app space name is required")
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(AppSpace).where(
                AppSpace.workspace_id == workspace_id, AppSpace.name == clean_name
            )
        )
        if existing is not None:
            raise ValidationError(f"app space {clean_name!r} already exists")
        space = AppSpace(
            workspace_id=workspace_id,
            name=clean_name,
            description=(description or "").strip() or None,
            api_scopes=json.dumps(_clean_scopes(api_scopes)),
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(space)
        try:
            session.commit()
        except IntegrityError as exc:
            # A concurrent create raced past the existence check above.
            session.rollback()
            raise ValidationError(f"app space {clean_name!r} already exists") from exc
        session.refresh(space)
        return _serialize(space, app_count=0)


def update_space(
    factory: sessionmaker[Session],
    *,
    space_id: int,
    workspace_id: int,
    description: str | None = None,
    api_scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Update a space's description and/or API scopes.

    Args:
        factory: Session factory.
        space_id: Target space.
        workspace_id: Owning workspace; a space in any other workspace is
            rejected as unknown.
        description: New description, when provided (``""`` clears it).
        api_scopes: New scope list, when provided.

    Returns:
        The serialized, updated space.

    Raises:
        ValidationError: When the space does not exist.
    """
    with factory() as session:
        space = session.get(AppSpace, space_id)
        if space is None or int(space.workspace_id) != workspace_id:
            raise ValidationError(f"app space {space_id} not found")
        if description is not None:
            space.description = description.strip() or None
        if api_scopes is not None:
            space.api_scopes = json.dumps(_clean_scopes(api_scopes))
        space.updated_at = _utcnow()
        counts = _app_counts(session, int(space.workspace_id))
        session.commit()
        session.refresh(space)
        return _serialize(space, app_count=counts.get(space.id, 0))


def delete_space(factory: sessionmaker[Session], *, space_id: int, workspace_id: int) -> bool:
    """Delete a space (member apps keep running, ungrouped).

    Args:
        factory: Session factory.
        space_id: Target space.
        workspace_id: Owning workspace; a space in any other workspace is
            left untouched and reported as no-match.

    Returns:
        ``True`` when a row was removed.
    """
    with factory() as session:
        space = session.get(AppSpace, space_id)
        if space is None or int(space.workspace_id) != workspace_id:
            return False
        # Detach member apps explicitly (SQLite SET NULL needs PRAGMA
        # foreign_keys; doing it here keeps the behaviour deterministic).
        for app in session.scalars(
            select(HostedApp).where(HostedApp.app_space_id == space_id)
        ).all():
            app.app_space_id = None
        session.delete(space)
        session.commit()
    return True


def assign_app(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    app_id: int,
    space_id: int | None,
) -> dict[str, Any]:
    """Assign a hosted app to a space (or detach it when ``space_id`` is None).

    Args:
        factory: Session factory.
        workspace_id: Active workspace (both app + space must belong).
        app_id: The hosted app to (re)assign.
        space_id: Target space, or ``None`` to ungroup the app.

    Returns:
        ``{"app_id", "app_space_id"}`` after the change.

    Raises:
        ValidationError: When the app or target space is unknown / in a
            different workspace.
    """
    with factory() as session:
        app = session.get(HostedApp, app_id)
        if app is None or int(app.workspace_id) != workspace_id:
            raise ValidationError(f"hosted app {app_id} not found")
        if space_id is not None:
            space = session.get(AppSpace, space_id)
            if space is None or int(space.workspace_id) != workspace_id:
                raise ValidationError(f"app space {space_id} not found")
        app.app_space_id = space_id
        app.updated_at = _utcnow()
        session.commit()
        return {"app_id": app_id, "app_space_id": space_id}


def effective_app_scopes(factory: sessionmaker[Session], *, app_id: int) -> dict[str, Any]:
    """Resolve a hosted app's effective API scopes from its space.

    Args:
        factory: Session factory.
        app_id: The hosted app.

    Returns:
        ``{"app_id", "space_id", "space_name", "api_scopes"}`` — empty
        scopes and ``None`` space when the app is ungrouped or unknown.
    """
    with factory() as session:
        app = session.get(HostedApp, app_id)
        if app is None or app.app_space_id is None:
            return {"app_id": app_id, "space_id": None, "space_name": None, "api_scopes": []}
        space = session.get(AppSpace, app.app_space_id)
        if space is None:
            return {"app_id": app_id, "space_id": None, "space_name": None, "api_scopes": []}
        return {
            "app_id": app_id,
            "space_id": space.id,
            "space_name": space.name,
            "api_scopes": _parse_scopes(space.api_scopes),
        }
