"""Event-stream output-port substrate: subscriptions + deliveries.

Two tables that back the runtime of declared ``kind='event'`` output
ports.  A subscription tracks one consumer's position in a product's
Delta Change Data Feed; each pump emits one delivery row recording the
``[version_from, version_to)`` window the hub fanned out.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Allowed values for :attr:`DataProductEventSubscription.status`.
EVENT_SUBSCRIPTION_STATUSES: tuple[str, ...] = ("active", "paused", "closed")

#: Allowed values for :attr:`DataProductEventDelivery.status`.
EVENT_DELIVERY_STATUSES: tuple[str, ...] = ("ok", "error", "empty")


class DataProductEventSubscription(Base):
    """Durable consumer subscription on one event output port.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE.
        output_port_id: FK on ``data_product_output_ports.id`` with
            CASCADE.  The port must be of kind ``'event'``; the
            service layer validates that at create.
        table_name: UC table whose CDF this subscription reads.
        consumer_label: Human-readable consumer name (unique per
            ``output_port_id + table_name``).
        position_marker_json: JSON
            ``{"version": int, "row_offset": int}`` cursor.
        status: One of :data:`EVENT_SUBSCRIPTION_STATUSES`.
        last_delivered_at: Wall-clock of the last successful pump,
            or ``None`` until the first delivery.
        owner_user_id: Nullable FK on ``users.id``.
        created_at: First-insert wall-clock.
    """

    __tablename__ = "data_product_event_subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "output_port_id",
            "consumer_label",
            "table_name",
            name="uq_dp_event_subs_identity",
        ),
        Index("ix_dp_event_subs_product", "data_product_id"),
        Index("ix_dp_event_subs_status", "status"),
        CheckConstraint(
            "status IN ('active','paused','closed')",
            name="ck_dp_event_subs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_port_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_output_ports.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str] = mapped_column(String(200), nullable=False)
    consumer_label: Mapped[str] = mapped_column(String(120), nullable=False)
    position_marker_json: Mapped[str] = mapped_column(
        Text, nullable=False, default='{"version": 0, "row_offset": 0}'
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    last_delivered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductEventDelivery(Base):
    """Per-pump audit row recording one CDF-fan-out window."""

    __tablename__ = "data_product_event_deliveries"

    __table_args__ = (
        Index(
            "ix_dp_event_deliveries_subscription",
            "subscription_id",
            "delivered_at",
        ),
        CheckConstraint(
            "status IN ('ok','error','empty')",
            name="ck_dp_event_deliveries_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_event_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_from: Mapped[int] = mapped_column(Integer, nullable=False)
    version_to: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
