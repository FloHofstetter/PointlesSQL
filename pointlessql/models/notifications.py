"""Per-user notification inbox (Phase 71.4).

One table:

* ``user_notifications`` — one row per recipient per fired event.
  Separate from ``governance_events`` (which is system-wide, one
  row per envelope): the inbox needs *N rows per envelope* (one
  per recipient) plus a per-user ``read_at`` state column.

Fan-out lives on the emit side (see
:mod:`pointlessql.services.notifications.fanout`).  Retention is
governed by the same Phase-20 ``audit_retention`` loop that prunes
``governance_events`` — no separate policy.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class UserNotification(Base):
    """One notification queued for one recipient.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        recipient_user_id: FK on ``users.id``.  Receives the row.
            ``ondelete='CASCADE'`` so removed users don't leave
            orphan inbox rows.
        event_type: One of the Phase-71.4 / Phase-20 governance
            event types.  Kept as ``String(80)`` so a producer can
            ship a new type without an Alembic migration on the
            recipient side.
        source_data_product_id: Optional FK on ``data_products.id``
            for click-through.  Nullable so the table can later
            absorb non-DP events without a schema change.
        source_entity_kind: Phase 77.0.D polymorphic discriminator —
            one of the kinds registered in :mod:`pointlessql.models.social`.
            ``None`` only on legacy rows written before the column
            existed.
        source_entity_ref: Reference within ``source_entity_kind``
            (FQN / id / slug, kind-dependent).  ``None`` only on
            legacy rows; the audit-trail recovery path uses
            ``source_data_product_id`` for those.
        source_url: Click-through URL (usually
            ``/data-products/{cat}/{sch}#tab-discussion`` or
            similar).
        summary_md: One-line markdown body rendered in the inbox.
        actor_user_id: Optional FK on ``users.id`` — who triggered
            the event (``None`` for system-emitted events like
            schema-change).
        read_at: ``None`` while unread, wall-clock once flipped.
        created_at: Wall-clock at fan-out time.
    """

    __tablename__ = "user_notifications"

    __table_args__ = (
        Index(
            "ix_user_notif_recipient_unread",
            "recipient_user_id",
            "read_at",
        ),
        Index(
            "ix_user_notif_recipient_created",
            "recipient_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    recipient_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Phase 77.0.D — polymorphic source markers.  Populated when
    # the row is fanned out via ``fanout_event(entity_kind=…,
    # entity_ref=…)``.  ``source_data_product_id`` stays as the
    # legacy back-compat path for kind='dp' rows so existing
    # client code that joins on it keeps working.
    source_entity_kind: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    source_entity_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    read_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserWebhookSubscription(Base):
    """Per-user CloudEvent webhook subscription (Phase 72.6).

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope (the user's "default" workspace
            is where the subscription lives).
        user_id: Owner — only this user can read / modify / delete.
        webhook_url: Delivery URL.  Limited to 1000 chars.
        hmac_secret: Plaintext HMAC secret, generated server-side
            at create time and returned to the caller ONCE in the
            create response.  Never echoed afterwards.
        event_type_filter: Either a fully-qualified event type
            (e.g. ``pointlessql.data_product.commented``) or
            ``"*"`` to match the entire ``pointlessql.data_product.*``
            family.
        dp_ref_filter: Optional ``"catalog.schema"`` filter; ``None``
            matches all data products.
        is_active: Toggle without delete.
        created_at: Wall-clock at create.
        last_delivered_at: Updated on each successful delivery.
        last_error: Updated on each failed delivery (text);
            cleared on the next success.
    """

    __tablename__ = "user_webhook_subscriptions"

    __table_args__ = (
        Index(
            "ix_user_webhook_sub_user_active",
            "user_id",
            "is_active",
        ),
        Index(
            "ix_user_webhook_sub_event_type",
            "event_type_filter",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    webhook_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    hmac_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type_filter: Mapped[str] = mapped_column(String(120), nullable=False)
    dp_ref_filter: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_delivered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
