"""Durable subscription CRUD + position-cursor math + delivery ledger."""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import (
    DataProductEventDelivery,
    DataProductEventSubscription,
    DataProductOutputPort,
)
from pointlessql.types import SessionFactory


def decode_position(payload: str | None) -> dict[str, int]:
    if not payload:
        return {"version": 0, "row_offset": 0}
    try:
        data = json.loads(payload)
    except TypeError, ValueError:
        return {"version": 0, "row_offset": 0}
    return {
        "version": int(data.get("version", 0)),
        "row_offset": int(data.get("row_offset", 0)),
    }


def _serialise(row: DataProductEventSubscription) -> dict[str, Any]:
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "output_port_id": row.output_port_id,
        "table_name": row.table_name,
        "consumer_label": row.consumer_label,
        "status": row.status,
        "position": decode_position(row.position_marker_json),
        "last_delivered_at": (row.last_delivered_at.isoformat() if row.last_delivered_at else None),
        "owner_user_id": row.owner_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def create_subscription(
    factory: SessionFactory,
    *,
    data_product_id: int,
    output_port_id: int,
    table_name: str,
    consumer_label: str,
    owner_user_id: int | None = None,
    start_version: int = 0,
) -> dict[str, Any]:
    """Create a durable subscription on an event output port.

    Args:
        factory: Sessionmaker callable.
        data_product_id: Product that owns the output port.
        output_port_id: PK of the ``kind='event'`` output port to
            subscribe to.
        table_name: CDF-enabled table the consumer reads changes
            from; stripped before storage.
        consumer_label: Caller-chosen consumer name; unique per
            (port, table) pair, stripped before storage.
        owner_user_id: Subscribing user's PK, or ``None``.
        start_version: Delta version the position cursor starts at.

    Returns:
        The serialised subscription row with ``status='active'``.

    Raises:
        ValueError: When the label/table are blank, the port is
            missing, belongs to another product, or is not of kind
            ``'event'``, or the (port, label, table) triple already
            exists.
    """
    cleaned_label = consumer_label.strip()
    cleaned_table = table_name.strip()
    if not cleaned_label or not cleaned_table:
        raise ValueError("consumer_label and table_name are required")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        port = session.get(DataProductOutputPort, output_port_id)
        if port is None:
            raise ValueError(f"output port id={output_port_id} not found")
        if port.kind != "event":
            raise ValueError(
                f"output port id={output_port_id} is not kind='event' (got {port.kind!r})"
            )
        if port.data_product_id != data_product_id:
            raise ValueError("output_port_id does not belong to the given data_product_id")
        existing = session.scalar(
            select(DataProductEventSubscription).where(
                DataProductEventSubscription.output_port_id == output_port_id,
                DataProductEventSubscription.consumer_label == cleaned_label,
                DataProductEventSubscription.table_name == cleaned_table,
            )
        )
        if existing is not None:
            raise ValueError(
                f"subscription {cleaned_label!r}/{cleaned_table!r} already exists "
                f"on port {output_port_id}"
            )
        row = DataProductEventSubscription(
            data_product_id=data_product_id,
            output_port_id=output_port_id,
            table_name=cleaned_table,
            consumer_label=cleaned_label,
            position_marker_json=json.dumps({"version": int(start_version), "row_offset": 0}),
            status="active",
            owner_user_id=owner_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialise(row)


def list_subscriptions(
    factory: SessionFactory,
    *,
    data_product_id: int | None = None,
    output_port_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return matching subscriptions newest-first."""
    with factory() as session:
        stmt = select(DataProductEventSubscription)
        if data_product_id is not None:
            stmt = stmt.where(DataProductEventSubscription.data_product_id == data_product_id)
        if output_port_id is not None:
            stmt = stmt.where(DataProductEventSubscription.output_port_id == output_port_id)
        if status is not None:
            stmt = stmt.where(DataProductEventSubscription.status == status)
        stmt = stmt.order_by(DataProductEventSubscription.id.desc())
        rows = list(session.scalars(stmt).all())
    return [_serialise(r) for r in rows]


def delete_subscription(factory: SessionFactory, *, subscription_id: int) -> bool:
    """Hard-delete one subscription.  Returns True when a row was removed."""
    with factory() as session:
        row = session.get(DataProductEventSubscription, subscription_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def pause_subscription(factory: SessionFactory, *, subscription_id: int) -> dict[str, Any] | None:
    """Set ``status='paused'``; return the serialised row or ``None``."""
    return _set_status(factory, subscription_id, "paused")


def resume_subscription(factory: SessionFactory, *, subscription_id: int) -> dict[str, Any] | None:
    """Set ``status='active'``; return the serialised row or ``None``."""
    return _set_status(factory, subscription_id, "active")


def _set_status(
    factory: SessionFactory, subscription_id: int, status: str
) -> dict[str, Any] | None:
    if status not in ("active", "paused", "closed"):
        raise ValueError(f"status {status!r} invalid")
    with factory() as session:
        row = session.get(DataProductEventSubscription, subscription_id)
        if row is None:
            return None
        row.status = status
        session.commit()
        session.refresh(row)
        return _serialise(row)


def rewind_subscription(
    factory: SessionFactory, *, subscription_id: int, to_version: int
) -> dict[str, Any] | None:
    """Move the cursor back to *to_version* with row offset 0."""
    if to_version < 0:
        raise ValueError("to_version must be >= 0")
    with factory() as session:
        row = session.get(DataProductEventSubscription, subscription_id)
        if row is None:
            return None
        row.position_marker_json = json.dumps({"version": int(to_version), "row_offset": 0})
        session.commit()
        session.refresh(row)
        return _serialise(row)


def advance_position(
    factory: SessionFactory,
    *,
    subscription_id: int,
    to_version: int,
    row_offset: int = 0,
) -> dict[str, Any] | None:
    """Advance the cursor forward.  Rejects backward movement.

    Args:
        factory: Sessionmaker callable.
        subscription_id: PK of the subscription whose cursor moves.
        to_version: Target Delta version; must be at or past the
            current cursor version.
        row_offset: Row position reached within *to_version*.

    Returns:
        The serialised subscription row with the updated cursor and
        ``last_delivered_at``, or ``None`` when the subscription does
        not exist.

    Raises:
        ValueError: When *to_version* or *row_offset* is negative, or
            *to_version* is less than the current version.
    """
    if to_version < 0 or row_offset < 0:
        raise ValueError("to_version and row_offset must be >= 0")
    with factory() as session:
        row = session.get(DataProductEventSubscription, subscription_id)
        if row is None:
            return None
        current = decode_position(row.position_marker_json)
        if to_version < current["version"]:
            raise ValueError(
                f"refusing to move cursor backwards "
                f"({current['version']} -> {to_version}); use rewind_subscription"
            )
        row.position_marker_json = json.dumps(
            {"version": int(to_version), "row_offset": int(row_offset)}
        )
        row.last_delivered_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        return _serialise(row)


def record_delivery(
    factory: SessionFactory,
    *,
    subscription_id: int,
    version_from: int,
    version_to: int,
    row_count: int,
    status: str,
) -> int:
    """Insert one :class:`DataProductEventDelivery` ledger row.

    Args:
        factory: Sessionmaker callable.
        subscription_id: PK of the subscription this delivery was for.
        version_from: Inclusive start version.
        version_to: Exclusive end version.
        row_count: Number of CDF rows fanned out in this window.
        status: One of ``'ok'`` / ``'error'`` / ``'empty'``.

    Returns:
        The delivery row's id.

    Raises:
        ValueError: When *status* is not one of the accepted values.
    """
    if status not in ("ok", "error", "empty"):
        raise ValueError(f"status {status!r} invalid")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = DataProductEventDelivery(
            subscription_id=subscription_id,
            version_from=int(version_from),
            version_to=int(version_to),
            row_count=int(row_count),
            delivered_at=now,
            status=status,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
