"""Alert-event recording, listing, and pruning."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, desc, select

from pointlessql.models import Alert, AlertEvent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def record_event(
    factory: sessionmaker[Session],
    *,
    alert_id: int,
    event_id: str,
    fired_at: datetime.datetime,
    row_count: int | None,
    outcome: str,
    payload_json: str,
) -> int:
    """Insert one :class:`AlertEvent` row, returning its PK.

    Args:
        factory: SQLAlchemy session factory.
        alert_id: Parent alert id.
        event_id: CloudEvents ``id`` (uuid4 hex).
        fired_at: Timestamp the check decided to fire.
        row_count: Query row count at firing time, or ``None``.
        outcome: ``fired`` / ``suppressed`` / ``delivery_failed``.
        payload_json: Serialised CloudEvents envelope.

    Returns:
        The new ``alert_events.id``.
    """
    with factory() as session:
        ev = AlertEvent(
            alert_id=alert_id,
            event_id=event_id,
            fired_at=fired_at,
            row_count=row_count,
            outcome=outcome,
            payload_json=payload_json,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)
        return ev.id


def set_event_outcome(factory: sessionmaker[Session], event_id: str, outcome: str) -> None:
    """Patch the ``outcome`` of a previously-recorded event.

    Args:
        factory: SQLAlchemy session factory.
        event_id: The CloudEvents ``id`` (``AlertEvent.event_id``).
        outcome: New outcome value.
    """
    with factory() as session:
        ev = session.scalar(select(AlertEvent).where(AlertEvent.event_id == event_id))
        if ev is not None:
            ev.outcome = outcome
            session.commit()


def list_events_for_alert(
    factory: sessionmaker[Session],
    alert_id: int,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent events for *alert_id* as dicts.

    Args:
        factory: SQLAlchemy session factory.
        alert_id: Parent alert id.
        limit: Hard row cap.

    Returns:
        List of dicts in newest-first order.
    """
    stmt = (
        select(AlertEvent)
        .where(AlertEvent.alert_id == alert_id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(limit)
    )
    with factory() as session:
        rows = session.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "alert_id": r.alert_id,
                "event_id": r.event_id,
                "fired_at": r.fired_at.isoformat() if r.fired_at else None,
                "row_count": r.row_count,
                "outcome": r.outcome,
                "payload_json": r.payload_json,
            }
            for r in rows
        ]


def list_events_for_owner(
    factory: sessionmaker[Session],
    owner_id: int,
    *,
    since: datetime.datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return events for every alert owned by *owner_id*.

    Used by the pull-feed endpoints.  Implicitly scopes to the caller
    because the feed token itself authenticates ownership.

    Args:
        factory: SQLAlchemy session factory.
        owner_id: Owner id whose alerts' events we surface.
        since: Floor on ``fired_at``.  ``None`` returns the full window.
        limit: Hard row cap.

    Returns:
        List of dicts sorted newest-first; each entry embeds the
        parent alert's slug + title for feed-renderer convenience.
    """
    stmt = (
        select(AlertEvent, Alert)
        .join(Alert, Alert.id == AlertEvent.alert_id)
        .where(Alert.owner_id == owner_id)
        .order_by(desc(AlertEvent.fired_at))
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(AlertEvent.fired_at >= since)
    with factory() as session:
        rows = session.execute(stmt).all()
        return [
            {
                "id": ev.id,
                "alert_id": ev.alert_id,
                "alert_slug": al.slug,
                "alert_title": al.title,
                "event_id": ev.event_id,
                "fired_at": ev.fired_at.isoformat() if ev.fired_at else None,
                "row_count": ev.row_count,
                "outcome": ev.outcome,
                "payload_json": ev.payload_json,
            }
            for ev, al in rows
        ]


def prune_events_older_than(factory: sessionmaker[Session], cutoff: datetime.datetime) -> int:
    """Delete ``alert_events`` rows with ``fired_at`` older than *cutoff*.

    Args:
        factory: SQLAlchemy session factory.
        cutoff: Timestamp threshold.

    Returns:
        The number of deleted rows.
    """
    with factory() as session:
        result = session.execute(delete(AlertEvent).where(AlertEvent.fired_at < cutoff))
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
