"""Data-quality monitoring — monitors, profile snapshots, anomalies.

Three tables backing the lakehouse-monitoring surface:

* ``quality_monitors`` — one monitor per row, pointed at either a
  single table FQN (``cat.sch.tbl``) or a whole schema prefix
  (``cat.sch``).  An active monitor owns a hidden scheduler ``Job``
  (kind ``"quality_monitor"``) that drives periodic scans.
* ``table_profile_snapshots`` — one per-table profile per scan: row
  count, Delta version, and per-column metrics (null / distinct
  counts, min / max / mean) as a JSON document.
* ``quality_anomalies`` — rule violations derived by comparing each
  fresh snapshot against its predecessor (volume drop, null spike,
  schema change) plus the freshness check.  Open anomalies carry
  ``resolved_at IS NULL``; a later scan that no longer trips the
  rule stamps the resolution timestamp.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

QUALITY_ANOMALY_KINDS: tuple[str, ...] = (
    "volume_drop",
    "null_spike",
    "schema_change",
    "freshness",
)
"""Anomaly rules the scan engine evaluates."""

QUALITY_ANOMALY_SEVERITIES: tuple[str, ...] = ("warn", "critical")
"""Severity ladder for detected anomalies."""


class QualityMonitor(Base):
    """One data-quality monitor over a table or schema prefix.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; monitors are
            workspace-scoped like the rest of the metadata DB.
        target: Either a three-part table FQN (``cat.sch.tbl``) or a
            two-part schema prefix (``cat.sch``) — the latter scans
            every table in the schema.  Unique per workspace.
        cron_expr: 5-field croniter expression driving the backing
            scheduler job.
        is_active: When ``True`` the backing job ticks on schedule;
            flipping to ``False`` pauses (not deletes) the job.
        backing_job_id: FK to ``jobs.id`` — the hidden scheduler job
            (kind ``"quality_monitor"``) that runs the scans.
        created_by_user_id: FK to ``users.id``; anomaly notifications
            are routed to this user.
        created_at: Timestamp when the monitor was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "quality_monitors"

    __table_args__ = (
        UniqueConstraint("workspace_id", "target", name="uq_quality_monitors_target"),
        Index("ix_quality_monitors_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    backing_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=True
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TableProfileSnapshot(Base):
    """One per-table profile captured by a monitor scan.

    Attributes:
        id: Auto-incremented primary key.
        monitor_id: FK to :class:`QualityMonitor` with ``ON DELETE
            CASCADE`` — snapshots follow their monitor.
        table_fqn: The profiled table's three-part name.
        delta_version: Delta log version at capture time, or ``None``
            when the table could not report one.
        row_count: Total rows observed.
        column_metrics: JSON object keyed by column name; each value
            carries ``null_count`` / ``distinct_count`` / ``min`` /
            ``max`` / ``mean``.
        captured_at: Wall-clock the profile was taken.
    """

    __tablename__ = "table_profile_snapshots"

    __table_args__ = (
        Index(
            "ix_table_profile_snapshots_lookup",
            "monitor_id",
            "table_fqn",
            text("captured_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quality_monitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_fqn: Mapped[str] = mapped_column(String(256), nullable=False)
    delta_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_metrics: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    captured_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QualityAnomaly(Base):
    """One detected rule violation on a monitored table.

    Attributes:
        id: Auto-incremented primary key.
        monitor_id: FK to :class:`QualityMonitor` with ``ON DELETE
            CASCADE``.
        table_fqn: The affected table's three-part name.
        column_name: The affected column for per-column rules
            (``null_spike``); ``None`` for table-level rules.
        kind: One of :data:`QUALITY_ANOMALY_KINDS`.
        severity: One of :data:`QUALITY_ANOMALY_SEVERITIES`.
        observed: Human-readable observed value (e.g. the new row
            count or null fraction).
        expected: Human-readable expectation the observation broke.
        detail: Free-form explanation (e.g. the added / removed
            column list for ``schema_change``).
        detected_at: Wall-clock of the first scan that tripped the
            rule.
        resolved_at: Wall-clock of the first scan where the rule no
            longer tripped; ``None`` while the anomaly is open.
    """

    __tablename__ = "quality_anomalies"

    __table_args__ = (
        Index("ix_quality_anomalies_monitor", "monitor_id"),
        Index("ix_quality_anomalies_open", "monitor_id", "table_fqn", "resolved_at"),
        CheckConstraint(
            "kind IN ('volume_drop', 'null_spike', 'schema_change', 'freshness')",
            name="ck_quality_anomalies_kind",
        ),
        CheckConstraint(
            "severity IN ('warn', 'critical')",
            name="ck_quality_anomalies_severity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quality_monitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_fqn: Mapped[str] = mapped_column(String(256), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    observed: Mapped[str] = mapped_column(String(400), nullable=False)
    expected: Mapped[str] = mapped_column(String(400), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
