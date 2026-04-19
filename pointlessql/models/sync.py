"""Foreign-catalog sync run history."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SyncRun(Base):
    """One execution record of a foreign-catalog sync.

    Written by :mod:`pointlessql.services.pg_sync` when a Postgres
    sync worker runs against a foreign catalog — either through the
    manual "Sync now" button (Sprint 18) or later on a schedule
    (Sprint 19).  Entries are append-only and double as the source
    for the history card on the catalog detail page.

    ``status`` cycles through ``running`` → ``succeeded`` | ``failed``.
    ``finished_at`` stays ``NULL`` while the run is in flight, which
    the UI renders as a spinner.  ``error`` carries the exception
    message when ``status == "failed"``.

    Attributes:
        id: Auto-incremented primary key.
        catalog_name: Target foreign catalog that was synced.
        started_at: Timestamp when the sync began.
        finished_at: Timestamp when the sync ended, or ``None`` while
            still running.
        status: ``running``, ``succeeded``, or ``failed``.
        added_count: Number of schemas + tables created during the run.
        changed_count: Number of tables whose columns were modified.
        dropped_count: Number of tables removed because the source
            Postgres no longer has them.
        error: Error message if ``status == "failed"``, else ``None``.
    """

    __tablename__ = "sync_run"

    __table_args__ = (
        Index("ix_sync_run_catalog_started", "catalog_name", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_name: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
