"""BI-dashboard refresh schedules and captured snapshots.

Two tables behind the scheduled-delivery surface of the AI/BI
dashboards:

* ``bi_dashboard_schedules`` — at most one cron schedule per
  dashboard.  Activation materialises a hidden backing
  :class:`~pointlessql.models.Job` (``kind="bi_snapshot"``) so the
  existing scheduler drives the refresh; delivery preferences
  (in-app notification, signed webhook) live on the schedule row.
* ``bi_dashboard_snapshots`` — one captured rendering of the whole
  dashboard: every widget's result set (or its error) frozen as a
  JSON payload, so the snapshot page replays the dashboard exactly
  as it looked at capture time without re-running any SQL.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

SNAPSHOT_TRIGGERS: tuple[str, ...] = ("schedule", "manual")
"""How a snapshot came to exist — cron tick or "Snapshot now"."""


class BiDashboardSchedule(Base):
    """The refresh schedule of one BI dashboard.

    Unique per dashboard: a dashboard either has one schedule or
    none, which keeps the upsert surface (one ``PUT`` per dashboard)
    and the backing-job lifecycle trivially 1:1.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; denormalised from the
            dashboard for workspace-scoped queries.
        dashboard_id: FK to ``bi_dashboards.id`` with ``ON DELETE
            CASCADE`` — the schedule follows its canvas.  Unique, so
            one dashboard carries at most one schedule.
        cron_expr: 5-field croniter expression.  Minute granularity.
        is_active: Inactive schedules pause (not delete) the backing
            job so run history survives a temporary switch-off.
        backing_job_id: FK to ``jobs.id``.  Materialised on first
            upsert; the hidden ``bi_snapshot`` job the scheduler
            ticks.
        deliver_inapp: When ``True`` every scheduled capture fans an
            in-app notification out to the dashboard owner.
        webhook_url: Optional delivery URL; every scheduled capture
            POSTs a CloudEvents envelope there.
        webhook_hmac_secret: Optional shared secret; when set the
            dispatcher signs the envelope body (HMAC-SHA256) so the
            receiver can verify origin.  Plaintext-at-rest, mirroring
            alert destinations.
        created_by_user_id: FK to ``users.id`` — the scheduling user;
            the backing job runs as this principal so SELECT
            enforcement applies to the snapshot queries.
        last_run_at: Wall-clock of the most recent scheduled capture,
            or ``None`` before the first one.
        created_at: Timestamp when the schedule was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "bi_dashboard_schedules"

    __table_args__ = (Index("ix_bi_dashboard_schedules_workspace", "workspace_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    dashboard_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bi_dashboards.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    backing_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=True
    )
    deliver_inapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    webhook_hmac_secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BiDashboardSnapshot(Base):
    """One frozen rendering of one BI dashboard.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; denormalised from the
            dashboard.
        dashboard_id: FK to ``bi_dashboards.id`` with ``ON DELETE
            CASCADE`` — snapshots follow their canvas.
        captured_at: Wall-clock when the capture ran.
        triggered_by: One of :data:`SNAPSHOT_TRIGGERS` — ``schedule``
            for cron captures, ``manual`` for the "Snapshot now"
            button.
        payload: JSON document ``{"title", "widgets": [{"widget_id",
            "kind", "title", "chart_spec", "markdown", "columns",
            "rows", "row_count", "truncated", "error"}]}``.  Stored
            verbatim so the snapshot page replays without touching
            any live table; a per-widget ``error`` keeps one broken
            query from invalidating the rest of the capture.
    """

    __tablename__ = "bi_dashboard_snapshots"

    __table_args__ = (
        Index(
            "ix_bi_dashboard_snapshots_dashboard_captured",
            "dashboard_id",
            text("captured_at DESC"),
        ),
        CheckConstraint(
            "triggered_by IN ('schedule', 'manual')",
            name="ck_bi_dashboard_snapshots_triggered_by",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    dashboard_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bi_dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
