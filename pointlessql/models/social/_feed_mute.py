"""``feed_mutes`` — per-user mute / snooze for feed items.

the feed page lets users hide noisy threads.  One
row per ``(user_id, entity_kind, entity_ref)`` mute.  Mute Thread
and Mute Author share the schema: author-muting uses
``entity_kind='user'`` with the user-id (stringified) in
``entity_ref`` so the feed filter is one table scan.

* Permanent mute → ``muted_until IS NULL``.
* Snooze → ``muted_until`` = absolute datetime in the future.

Re-muting the same target updates the row's ``muted_until`` rather
than duplicating, enforced by the
``uq_feed_mutes_per_target`` unique index.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from pointlessql.models.base import Base


class FeedMute(Base):
    """One mute or snooze entry on a feed-visible entity.

    Attributes:
        id: Auto-incremented primary key.
        user_id: FK to ``users.id`` — the user whose feed is muted.
            Cascades on delete.
        entity_kind: Discriminator from
            :mod:`pointlessql.services.social.entity_registry` plus
            ``user`` for author-muting.  Kept as a free-form string
            to allow future kinds without schema churn.
        entity_ref: Entity reference — fqn / id / slug, kind-dependent.
            For ``entity_kind='user'`` carries the muted user-id as
            a stringified integer.
        muted_until: ``None`` for permanent mute, or the absolute UTC
            timestamp at which the mute lapses (Snooze semantics).
        created_at: Server-default ``now()`` so callers don't need to
            pass timestamps.
    """

    __tablename__ = "feed_mutes"

    __table_args__ = (
        Index(
            "uq_feed_mutes_per_target",
            "user_id",
            "entity_kind",
            "entity_ref",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    muted_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
