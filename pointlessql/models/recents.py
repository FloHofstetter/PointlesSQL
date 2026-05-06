"""Recent-table tracking for the catalog browser.

 surfaced a "Recent tables" block in the sidebar tree
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
        workspace_id: FK to :class:`Workspace`.  Recents are
            per-(workspace, user); the same user can have different
            recents per workspace.
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
            "workspace_id",
            "user_id",
            "table_full_name",
            name="uq_recent_tables_user_table",
        ),
        Index(
            "ix_recent_tables_user_last_visited",
            "user_id",
            "last_visited_at",
        ),
        Index(
            "ix_recent_tables_workspace_user",
            "workspace_id",
            "user_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Recents are per-(workspace, user) so the same user can have
    # different recents per workspace.  UNIQUE constraint widens to
    # include workspace_id.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    last_visited_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
