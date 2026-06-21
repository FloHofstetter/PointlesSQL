"""Snapshots / branches of a synced table's serving copy.

Lakebase's git-style branching makes instant copy-on-write copies of a
serving database so teams can experiment on production-like data.  The
copy-on-write storage engine itself is out of PointlesSQL's scope; what
PointlesSQL owns is the *management* layer — a registry of named
snapshots (and branches) over a :class:`SyncedTable`, each capturing the
Delta version + row count the mirror held at snapshot time, plus the
promote / discard lifecycle a human drives.

One row per snapshot in our own metadata DB; the serving Postgres mirror
is never written from here.
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

SNAPSHOT_STATUSES: tuple[str, ...] = ("active", "promoted", "discarded")
"""Lifecycle states for a synced-table snapshot.

``active`` is a live snapshot; ``promoted`` marks the one a human chose
as the serving baseline; ``discarded`` is a tombstoned snapshot kept for
audit.  Mirrored to a CHECK constraint.
"""


class SyncedTableSnapshot(Base):
    """One named snapshot / branch of a synced table's serving copy.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; snapshots inherit the
            synced table's workspace scope.
        synced_table_id: FK to ``synced_tables.id``; the snapshot's
            owning online table.  Cascade-deletes with it.
        name: Snapshot / branch identifier, unique per synced table.
        source_version: The source Delta version the mirror held when
            the snapshot was taken (``None`` when never synced).
        rows_snapshot: The mirror's lifetime row count at snapshot time.
        status: One of :data:`SNAPSHOT_STATUSES`.
        note: Free-text rationale shown in the UI.
        created_by: E-mail of the creating principal.
        created_at: Timestamp when the snapshot was taken.
        updated_at: Timestamp of the most recent status change.
    """

    __tablename__ = "synced_table_snapshots"

    __table_args__ = (
        UniqueConstraint("synced_table_id", "name", name="uq_synced_table_snapshots_table_name"),
        Index("ix_synced_table_snapshots_table", "synced_table_id"),
        CheckConstraint(
            "status IN ('active', 'promoted', 'discarded')",
            name="ck_synced_table_snapshots_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    synced_table_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("synced_tables.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
