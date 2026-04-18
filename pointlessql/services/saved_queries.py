"""Persistence + visibility helpers for the Phase-12 saved queries.

Visibility rules (Sprint 51 design):

- Owner + admin see every saved-query row the owner created,
  shared or private.
- Any other logged-in user sees the row only when
  ``is_shared`` is ``True``.
- Mutations (PATCH / DELETE / toggle sharing) are restricted to
  owner + admin.

The caller passes the current user in from the request layer;
the service never touches FastAPI directly so it stays easy to
unit-test.
"""

from __future__ import annotations

import datetime
import re
import secrets
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, or_, select

from pointlessql.exceptions import ValidationError
from pointlessql.models import SavedQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_SLUG_SANITIZER = re.compile(r"[^a-z0-9-]+")


def make_slug(title: str) -> str:
    """Derive a URL-safe slug from *title* with random suffix.

    ``slugify`` is a pure function: trim → lowercase → replace
    non-alphanumeric runs with hyphens → trim trailing hyphens.
    A 6-char hex random suffix then guarantees uniqueness even
    when two users happen to save queries with the same title
    ("daily-orders").  200-char ceiling matches the
    :class:`~pointlessql.models.SavedQuery.slug` column width.

    Args:
        title: The user-entered title.

    Returns:
        A URL-safe slug ending in a random 6-char token.
    """
    base = (title or "query").strip().lower()
    base = _SLUG_SANITIZER.sub("-", base).strip("-")
    if not base:
        base = "query"
    # Reserve 7 chars for the suffix + hyphen.
    max_base = 200 - 7
    if len(base) > max_base:
        base = base[:max_base].rstrip("-")
    return f"{base}-{secrets.token_hex(3)}"


def _can_view(row: SavedQuery, user_id: int, is_admin: bool) -> bool:
    """Return whether *user* can see the given row.

    Args:
        row: The saved-query row to check.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.

    Returns:
        ``True`` iff the user may see this row per the visibility
        rules (owner + admin + shared).
    """
    return is_admin or row.owner_id == user_id or row.is_shared


def _can_mutate(row: SavedQuery, user_id: int, is_admin: bool) -> bool:
    """Return whether *user* can edit / delete / re-share *row*.

    Args:
        row: The saved-query row.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.

    Returns:
        ``True`` iff the user is the owner or an administrator.
    """
    return is_admin or row.owner_id == user_id


def serialize(row: SavedQuery) -> dict[str, Any]:
    """Convert a row to the JSON-friendly dict used in API responses.

    Args:
        row: The saved-query row.

    Returns:
        A plain dict with scalar keys ready for ``JSONResponse``.
    """
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "sql_text": row.sql_text,
        "owner_id": row.owner_id,
        "is_shared": row.is_shared,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_saved_query(
    factory: sessionmaker[Session],
    *,
    owner_id: int,
    title: str,
    description: str | None,
    sql_text: str,
    is_shared: bool = False,
) -> dict[str, Any]:
    """Insert a new saved-query row.

    Args:
        factory: SQLAlchemy session factory.
        owner_id: ID of the user saving the query.
        title: Human-readable title (must be non-empty).
        description: Optional description.
        sql_text: The SQL to save.  Must be non-empty.
        is_shared: Whether the row is visible to other users.

    Returns:
        The serialised row as a dict.

    Raises:
        ValidationError: If *title* or *sql_text* is empty.
    """
    clean_title = (title or "").strip()
    if not clean_title:
        raise ValidationError("Title must not be empty.")
    clean_sql = (sql_text or "").strip()
    if not clean_sql:
        raise ValidationError("SQL must not be empty.")
    clean_description = description.strip() if description else None
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = SavedQuery(
            slug=make_slug(clean_title),
            title=clean_title[:200],
            description=clean_description,
            sql_text=clean_sql,
            owner_id=owner_id,
            is_shared=is_shared,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize(row)


def list_visible(
    factory: sessionmaker[Session],
    *,
    user_id: int,
    is_admin: bool,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return every saved query visible to the current user.

    Admin sees all rows; a regular user sees their own plus anything
    ``is_shared``.  Ordered by ``updated_at DESC`` so the most recent
    edits float to the top of the drawer.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.
        limit: Maximum rows to return.

    Returns:
        List of serialised row dicts.
    """
    stmt = select(SavedQuery).order_by(desc(SavedQuery.updated_at)).limit(limit)
    if not is_admin:
        stmt = stmt.where(or_(SavedQuery.owner_id == user_id, SavedQuery.is_shared))
    with factory() as session:
        rows = session.scalars(stmt).all()
        return [serialize(r) for r in rows]


def get_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
) -> dict[str, Any] | None:
    """Return the saved query at *slug* if the user may see it.

    Args:
        factory: SQLAlchemy session factory.
        slug: The URL-safe identifier.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.

    Returns:
        The serialised row, or ``None`` if either no row exists at
        that slug *or* the user lacks visibility (the two cases are
        indistinguishable to callers on purpose, so unguessable
        slugs double as a mild privacy guard for private queries).
    """
    with factory() as session:
        row = session.scalar(select(SavedQuery).where(SavedQuery.slug == slug))
        if row is None or not _can_view(row, user_id, is_admin):
            return None
        return serialize(row)


def update_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
    title: str | None = None,
    description: str | None = None,
    sql_text: str | None = None,
    is_shared: bool | None = None,
) -> dict[str, Any] | None:
    """Update mutable fields on a saved-query row.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target row's slug.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.
        title: New title, or ``None`` to leave unchanged.
        description: New description, or ``None`` to leave unchanged.
            Passing an explicit ``""`` clears it.
        sql_text: New SQL, or ``None`` to leave unchanged.
        is_shared: New sharing flag, or ``None`` to leave unchanged.

    Returns:
        The updated row as a dict, or ``None`` if the row does not
        exist or the user lacks mutate rights.

    Raises:
        ValidationError: If a non-``None`` *title* or *sql_text* is
            supplied but resolves to an empty string.
    """
    with factory() as session:
        row = session.scalar(select(SavedQuery).where(SavedQuery.slug == slug))
        if row is None or not _can_mutate(row, user_id, is_admin):
            return None
        if title is not None:
            clean = title.strip()
            if not clean:
                raise ValidationError("Title must not be empty.")
            row.title = clean[:200]
        if description is not None:
            row.description = description.strip() or None
        if sql_text is not None:
            clean = sql_text.strip()
            if not clean:
                raise ValidationError("SQL must not be empty.")
            row.sql_text = clean
        if is_shared is not None:
            row.is_shared = bool(is_shared)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        return serialize(row)


def delete_by_slug(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Delete the saved-query row at *slug*.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target row's slug.
        user_id: ID of the current user.
        is_admin: Whether the current user is an administrator.

    Returns:
        ``True`` iff a row was found, the user could mutate it, and
        it was deleted.  ``False`` if no row exists at that slug or
        the user is not owner/admin.
    """
    with factory() as session:
        row = session.scalar(select(SavedQuery).where(SavedQuery.slug == slug))
        if row is None or not _can_mutate(row, user_id, is_admin):
            return False
        session.delete(row)
        session.commit()
        return True
