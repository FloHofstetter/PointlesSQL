"""Add / remove webhook + feed destinations on an alert."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.exceptions import ValidationError
from pointlessql.models import Alert, AlertDestination
from pointlessql.services.alerts.crud import can_mutate, serialize_destination

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_VALID_KINDS = {"webhook", "feed"}


def add_destination(
    factory: sessionmaker[Session],
    slug: str,
    *,
    user_id: int,
    is_admin: bool,
    kind: str,
    webhook_url: str | None = None,
    hmac_secret: str | None = None,
) -> dict[str, Any] | None:
    """Attach a new destination to the alert at *slug*.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target alert slug.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.
        kind: ``webhook`` or ``feed``.
        webhook_url: Required when ``kind == "webhook"``.
        hmac_secret: Optional shared secret for webhook signing.

    Returns:
        The new destination dict, or ``None`` if the alert is absent
        or not mutable by the caller.

    Raises:
        ValidationError: On unknown *kind* or webhook without URL.
    """
    if kind not in _VALID_KINDS:
        raise ValidationError(f"kind must be one of {sorted(_VALID_KINDS)}.")
    if kind == "webhook" and not (webhook_url or "").strip():
        raise ValidationError("webhook destinations require webhook_url.")
    with factory() as session:
        alert = session.scalar(select(Alert).where(Alert.slug == slug))
        if alert is None or not can_mutate(alert, user_id, is_admin):
            return None
        dest = AlertDestination(
            alert_id=alert.id,
            kind=kind,
            webhook_url=(webhook_url or "").strip() or None,
            hmac_secret=(hmac_secret or "").strip() or None,
            is_active=True,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(dest)
        session.commit()
        session.refresh(dest)
        return serialize_destination(dest)


def delete_destination(
    factory: sessionmaker[Session],
    slug: str,
    destination_id: int,
    *,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Remove a destination from the alert at *slug*.

    Args:
        factory: SQLAlchemy session factory.
        slug: Target alert slug.
        destination_id: Target destination row id.
        user_id: Caller's user id.
        is_admin: Whether the caller is an administrator.

    Returns:
        ``True`` iff a matching row was deleted.
    """
    with factory() as session:
        alert = session.scalar(select(Alert).where(Alert.slug == slug))
        if alert is None or not can_mutate(alert, user_id, is_admin):
            return False
        dest = session.scalar(
            select(AlertDestination).where(
                AlertDestination.id == destination_id,
                AlertDestination.alert_id == alert.id,
            )
        )
        if dest is None:
            return False
        session.delete(dest)
        session.commit()
        return True
