"""Synced tables — reverse-ETL from Delta tables into a serving store.

One table backing the online-tables surface: each row names a UC
Delta table (the source) and a SQLAlchemy target URL + table (the
low-latency copy) and tracks the sync lifecycle.  The copy worker
itself lives in :mod:`pointlessql.services.synced_tables`; rows
survive restarts, and the Delta version cursor on the row is what
makes incremental (CDF) syncs resumable.
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

SYNCED_TABLE_MODES: tuple[str, ...] = ("full", "cdf")
"""Sync strategies: full snapshot replace vs. Change-Data-Feed apply."""

SYNCED_TABLE_STATUSES: tuple[str, ...] = ("idle", "syncing", "ok", "failed")
"""Sync lifecycle states the UI renders."""


class SyncedTable(Base):
    """One Delta table mirrored into a low-latency SQL target.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; synced tables are
            workspace-scoped like the rest of the metadata DB.
        name: Synced-table identifier, unique per workspace; appears
            in the sync and lookup URLs.
        source_fqn: Three-part UC name (``catalog.schema.table``) of
            the source Delta table.
        target_url: SQLAlchemy URL of the serving database.  May
            carry ``{{secrets/<scope>/<key>}}`` placeholders — the
            row stores the placeholder verbatim and the worker
            resolves it just-in-time, so credentials never rest here.
        target_table: Table name written in the target database.
        primary_keys: Comma-separated key columns.  Required for
            ``cdf`` mode (delete/upsert application) and the columns
            the lookup API may filter on.
        mode: One of :data:`SYNCED_TABLE_MODES` — ``full`` replaces
            the target on every sync, ``cdf`` applies Delta Change
            Data Feed events incrementally.
        last_synced_version: Delta version cursor — the highest
            source version already applied to the target.  ``None``
            until the first successful sync.
        status: One of :data:`SYNCED_TABLE_STATUSES`.
        last_error: Most recent sync failure, for the list page.
        rows_synced: Lifetime number of rows written to the target.
        last_synced_at: Wall-clock of the most recent successful sync.
        created_by: E-mail of the creating principal.
        created_at: Timestamp when the synced table was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "synced_tables"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_synced_tables_ws_name"),
        Index("ix_synced_tables_workspace", "workspace_id"),
        CheckConstraint(
            "mode IN ('full', 'cdf')",
            name="ck_synced_tables_mode",
        ),
        CheckConstraint(
            "status IN ('idle', 'syncing', 'ok', 'failed')",
            name="ck_synced_tables_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_fqn: Mapped[str] = mapped_column(String(768), nullable=False)
    target_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    target_table: Mapped[str] = mapped_column(String(256), nullable=False)
    primary_keys: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="full", server_default="full"
    )
    last_synced_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="idle", server_default="idle"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_synced_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
