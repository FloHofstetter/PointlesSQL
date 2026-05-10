"""Lens session CRUD — workspace + owner scoped.

Every helper here scopes by ``(workspace_id, owner_id)`` to enforce
the visibility model: a Lens session is owned by one analyst, never
shared, never visible cross-workspace.  Admin reads (the cockpit
view) bypass the owner filter via ``include_all=True``.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import LensSession

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def create_session(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_id: int,
    title: str,
    llm_provider: str,
    llm_model: str,
) -> LensSession:
    """Persist a fresh Lens session and return the detached row.

    The session is created with ``total_cost_estimate=0`` and
    ``last_message_at=NULL``; both are touched as messages append.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace the session belongs to.
        owner_id: User id of the session owner.
        title: Short human label.  Truncated to 200 chars.
        llm_provider: One of :data:`LENS_PROVIDERS`.
        llm_model: Provider-specific model identifier.

    Returns:
        The detached :class:`LensSession` row.
    """
    now = datetime.datetime.now(datetime.UTC)
    row = LensSession(
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=(title or "Untitled session")[:200],
        llm_provider=llm_provider,
        llm_model=llm_model,
        total_cost_estimate=0.0,
        created_at=now,
        updated_at=now,
        last_message_at=None,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def get_session(
    factory: sessionmaker[Session],
    *,
    session_id: int,
    workspace_id: int,
    owner_id: int | None = None,
) -> LensSession:
    """Return one session by id, enforcing workspace + owner scope.

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Lens session primary key.
        workspace_id: Workspace the caller is bound to.  Cross-
            workspace reads return :class:`ResourceNotFoundError`
            (not :class:`AuthorizationError` — Lens hides the
            existence of cross-workspace sessions to avoid info
            leak).
        owner_id: When set, requires the session to be owned by
            this user.  ``None`` for admin reads that bypass the
            owner filter.

    Returns:
        The detached :class:`LensSession` row.

    Raises:
        ResourceNotFoundError: When no row matches the scope filters.
    """
    with factory() as session:
        stmt = select(LensSession).where(
            LensSession.id == session_id,
            LensSession.workspace_id == workspace_id,
        )
        if owner_id is not None:
            stmt = stmt.where(LensSession.owner_id == owner_id)
        row = session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError(f"lens_session: {session_id}")
        session.expunge(row)
        return row


def list_sessions(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_id: int | None = None,
    limit: int = 50,
) -> list[LensSession]:
    """List sessions for sidebar display, newest activity first.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Workspace filter.
        owner_id: Owner filter.  ``None`` returns every session in
            the workspace (admin cockpit view).
        limit: Cap on rows returned.

    Returns:
        Detached rows, ordered by ``COALESCE(last_message_at,
        created_at) DESC``.
    """
    with factory() as session:
        stmt = (
            select(LensSession)
            .where(LensSession.workspace_id == workspace_id)
            .order_by(
                LensSession.last_message_at.desc().nulls_last(),
                LensSession.created_at.desc(),
            )
            .limit(limit)
        )
        if owner_id is not None:
            stmt = stmt.where(LensSession.owner_id == owner_id)
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def touch_session(
    factory: sessionmaker[Session],
    *,
    session_id: int,
) -> None:
    """Bump ``updated_at`` and ``last_message_at`` on the session.

    Called from :func:`append_message` after every persisted message
    so the sidebar order stays fresh.

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Lens session primary key.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.get(LensSession, session_id)
        if row is None:
            return
        row.updated_at = now
        row.last_message_at = now
        session.commit()


def update_session_cost(
    factory: sessionmaker[Session],
    *,
    session_id: int,
    delta: float,
) -> None:
    """Add *delta* to ``total_cost_estimate``.

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Lens session primary key.
        delta: Cost delta (positive — cost only increases).
    """
    if delta <= 0:
        return
    with factory() as session:
        row = session.get(LensSession, session_id)
        if row is None:
            return
        row.total_cost_estimate = float(row.total_cost_estimate) + float(delta)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()


def delete_session(
    factory: sessionmaker[Session],
    *,
    session_id: int,
    workspace_id: int,
    owner_id: int | None = None,
) -> bool:
    """Delete one session (cascade drops every message).

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Lens session primary key.
        workspace_id: Workspace the caller is bound to.
        owner_id: When set, only the owning user can delete.

    Returns:
        ``True`` when a row was deleted.
    """
    with factory() as session:
        stmt = delete(LensSession).where(
            LensSession.id == session_id,
            LensSession.workspace_id == workspace_id,
        )
        if owner_id is not None:
            stmt = stmt.where(LensSession.owner_id == owner_id)
        result = session.execute(stmt)
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0) > 0
