"""Recent-table tracking for the catalog browser (Sprint 17.5.1).

Sprint 17.5 surfaced a "Recent tables" block in the sidebar tree
backed by ``localStorage['pql.recentTables']``.  That works for a
single browser on a single device but breaks the moment a user
opens PointlesSQL on a second machine — the recents follow neither
the user nor the install.

This module backs the same UX with a server-side row per
``(user, table_full_name)`` so recents survive across devices and
sessions.  The table is intentionally narrow: no per-visit
counters, no "last opened from" attribution — just a sortable
``last_visited_at`` per pair.

The auto-write hook lives in the catalog-detail HTML handler,
which calls :func:`pointlessql.services.recents.record_table_visit`
after the page renders successfully.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class RecentTable(Base):
    """One row per ``(user, table)`` pair the user has visited.

    Attributes:
        id: Auto-incremented primary key.
        user_id: FK to ``users.id``.  Cascade-delete: removing a user
            also removes their recents (they're personal — no
            shared-state concern).
        table_full_name: Three-part ``catalog.schema.table`` identifier.
        last_visited_at: UTC timestamp of the most recent visit.
            Index supports ``ORDER BY DESC LIMIT 5`` per user.
    """

    __tablename__ = "recent_tables"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "table_full_name",
            name="uq_recent_tables_user_table",
        ),
        Index(
            "ix_recent_tables_user_last_visited",
            "user_id",
            "last_visited_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    last_visited_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
