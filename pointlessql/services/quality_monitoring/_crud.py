"""Quality-monitor CRUD + serialisation + backing-Job lifecycle.

Owns:

* target validation (table FQN or schema prefix) and the
  serialisation helpers shared with the routes;
* the monitor ``Job`` lifecycle (:func:`_sync_backing_job`) that
  drives the scheduler when ``is_active`` flips — mirroring the
  alert-check job lifecycle;
* the public CRUD surface plus the snapshot / anomaly read paths the
  API exposes.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, desc, func, select

from pointlessql.exceptions import ValidationError
from pointlessql.models import Job, JobLog, JobRun
from pointlessql.models.quality_monitoring import (
    QualityAnomaly,
    QualityMonitor,
    TableProfileSnapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

# A monitor target is either ``catalog.schema`` (scan every table in
# the schema) or ``catalog.schema.table`` (scan one table).
_TARGET_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?$")


def validate_target(target: str) -> str:
    """Validate and normalise a monitor target.

    Args:
        target: Candidate target string.

    Returns:
        The stripped target.

    Raises:
        ValidationError: When the target is neither a two-part schema
            prefix nor a three-part table FQN.
    """
    clean = (target or "").strip()
    if not _TARGET_RE.match(clean):
        raise ValidationError(
            "target must be catalog.schema (schema scan) or "
            f"catalog.schema.table (single table), got {clean!r}"
        )
    return clean


def serialize_monitor(row: QualityMonitor, *, open_anomalies: int = 0) -> dict[str, Any]:
    """Convert a :class:`QualityMonitor` to a JSON-friendly dict.

    Args:
        row: The monitor row.
        open_anomalies: Pre-computed count of unresolved anomalies.

    Returns:
        Dict shape consumed by the API routes and templates.
    """
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "target": row.target,
        "cron_expr": row.cron_expr,
        "is_active": row.is_active,
        "backing_job_id": row.backing_job_id,
        "created_by_user_id": row.created_by_user_id,
        "open_anomalies": open_anomalies,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_snapshot(row: TableProfileSnapshot) -> dict[str, Any]:
    """Convert a :class:`TableProfileSnapshot` to a JSON-friendly dict.

    Args:
        row: The snapshot row.

    Returns:
        Dict with the column metrics parsed back into an object.
    """
    return {
        "id": row.id,
        "monitor_id": row.monitor_id,
        "table_fqn": row.table_fqn,
        "delta_version": row.delta_version,
        "row_count": row.row_count,
        "column_metrics": json.loads(row.column_metrics or "{}"),
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
    }


def serialize_anomaly(row: QualityAnomaly) -> dict[str, Any]:
    """Convert a :class:`QualityAnomaly` to a JSON-friendly dict.

    Args:
        row: The anomaly row.

    Returns:
        Dict shape consumed by the API routes and templates.
    """
    return {
        "id": row.id,
        "monitor_id": row.monitor_id,
        "table_fqn": row.table_fqn,
        "column_name": row.column_name,
        "kind": row.kind,
        "severity": row.severity,
        "observed": row.observed,
        "expected": row.expected,
        "detail": row.detail,
        "detected_at": row.detected_at.isoformat() if row.detected_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def _create_backing_job(
    session: Session, monitor: QualityMonitor, now: datetime.datetime, *, paused: bool
) -> None:
    """Insert the hidden scheduler Job for *monitor* and link it.

    Args:
        session: Active SQLAlchemy session (caller commits).
        monitor: The monitor getting a job (must be flushed — its id
            seeds the job name and config).
        now: Creation timestamp.
        paused: Whether the job starts paused (inactive monitors that
            still want manual runs).
    """
    job = Job(
        workspace_id=monitor.workspace_id,
        name=f"quality-monitor:{monitor.id}",
        cron_expr=monitor.cron_expr,
        run_as_user_id=monitor.created_by_user_id,
        kind="quality_monitor",
        config=json.dumps({"monitor_id": monitor.id}, sort_keys=True),
        is_paused=paused,
        max_parallel_runs=1,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    session.flush()
    monitor.backing_job_id = job.id


def _sync_backing_job(session: Session, monitor: QualityMonitor) -> None:
    """Materialise / update / retire the scheduler Job for *monitor*.

    Lifecycle (mirrors the alert-check job lifecycle):

    - ``is_active=True`` and no backing job → create one.
    - ``is_active=True`` and a backing job exists → sync ``cron_expr``
      and un-pause.
    - ``is_active=False`` and a backing job exists → pause it (so the
      scheduler skips ticks) without deleting so history is preserved.
    - ``is_active=False`` and no backing job → nothing to do.

    Args:
        session: Active SQLAlchemy session (caller commits).
        monitor: The monitor whose lifecycle just changed.
    """
    now = datetime.datetime.now(datetime.UTC)
    job: Job | None = None
    if monitor.backing_job_id is not None:
        job = session.get(Job, monitor.backing_job_id)
    if monitor.is_active:
        if job is None:
            _create_backing_job(session, monitor, now, paused=False)
        else:
            job.cron_expr = monitor.cron_expr
            job.is_paused = False
            job.updated_at = now
    elif job is not None:
        job.is_paused = True
        job.updated_at = now


def ensure_backing_job(
    factory: sessionmaker[Session], monitor_id: int, *, workspace_id: int
) -> int | None:
    """Return the monitor's backing-job id, materialising one if needed.

    The manual "scan now" route runs through the scheduler's
    ``execute_run``, which needs a Job row.  A monitor created
    inactive has none yet — this creates it paused so the scheduler
    loop keeps skipping it while manual runs work.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: Primary key.
        workspace_id: Active workspace.

    Returns:
        The backing job id, or ``None`` when the monitor is absent.
    """
    with factory() as session:
        row = session.get(QualityMonitor, monitor_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        if row.backing_job_id is None:
            now = datetime.datetime.now(datetime.UTC)
            _create_backing_job(session, row, now, paused=not row.is_active)
            row.updated_at = now
            session.commit()
        return row.backing_job_id


def create_monitor(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    target: str,
    cron_expr: str,
    created_by_user_id: int,
    is_active: bool = True,
) -> dict[str, Any]:
    """Insert a new monitor, plus its backing scheduler Job when active.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Owning workspace.
        target: Table FQN or schema prefix to scan.
        cron_expr: 5-field croniter expression.
        created_by_user_id: Creator — the backing job runs as this
            user and anomaly notifications route to them.
        is_active: When ``True`` the backing Job is created right away.

    Returns:
        The serialised monitor.

    Raises:
        ValidationError: When the target is malformed, the cron
            expression is empty, or the workspace already monitors
            this target.
    """
    clean_target = validate_target(target)
    clean_cron = (cron_expr or "").strip()
    if not clean_cron:
        raise ValidationError("cron_expr must not be empty.")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(
            select(QualityMonitor.id).where(
                QualityMonitor.workspace_id == workspace_id,
                QualityMonitor.target == clean_target,
            )
        )
        if existing is not None:
            raise ValidationError(f"A monitor for {clean_target!r} already exists.")
        monitor = QualityMonitor(
            workspace_id=workspace_id,
            target=clean_target,
            cron_expr=clean_cron[:120],
            is_active=bool(is_active),
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(monitor)
        session.flush()
        _sync_backing_job(session, monitor)
        session.commit()
        session.refresh(monitor)
        return serialize_monitor(monitor)


def _open_anomaly_counts(session: Session, monitor_ids: list[int]) -> dict[int, int]:
    """Return ``monitor_id → open-anomaly count`` for *monitor_ids*.

    Args:
        session: Active SQLAlchemy session.
        monitor_ids: Monitors to count for.

    Returns:
        Mapping with an entry for every monitor that has at least one
        open anomaly; absent ids mean zero.
    """
    if not monitor_ids:
        return {}
    rows = session.execute(
        select(QualityAnomaly.monitor_id, func.count(QualityAnomaly.id))
        .where(
            QualityAnomaly.monitor_id.in_(monitor_ids),
            QualityAnomaly.resolved_at.is_(None),
        )
        .group_by(QualityAnomaly.monitor_id)
    ).all()
    return {int(mid): int(count) for mid, count in rows}


def list_monitors(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """Return the workspace's monitors, newest-updated first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace.

    Returns:
        Serialised monitors with their open-anomaly counts.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(QualityMonitor)
                .where(QualityMonitor.workspace_id == workspace_id)
                .order_by(desc(QualityMonitor.updated_at))
            )
        )
        counts = _open_anomaly_counts(session, [row.id for row in rows])
        return [serialize_monitor(row, open_anomalies=counts.get(row.id, 0)) for row in rows]


def get_monitor(
    factory: sessionmaker[Session], monitor_id: int, *, workspace_id: int
) -> dict[str, Any] | None:
    """Return one monitor by id within the workspace, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: Primary key.
        workspace_id: Active workspace.

    Returns:
        The serialised monitor, or ``None`` when absent.
    """
    with factory() as session:
        row = session.get(QualityMonitor, monitor_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        counts = _open_anomaly_counts(session, [row.id])
        return serialize_monitor(row, open_anomalies=counts.get(row.id, 0))


def update_monitor(
    factory: sessionmaker[Session],
    monitor_id: int,
    *,
    workspace_id: int,
    target: str | None = None,
    cron_expr: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    """Patch a monitor in place and re-sync its backing Job.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: Primary key.
        workspace_id: Active workspace.
        target: New target, or ``None`` to leave unchanged.
        cron_expr: New cron expression, or ``None``.
        is_active: New active flag, or ``None``.

    Returns:
        The updated monitor dict, or ``None`` when absent.

    Raises:
        ValidationError: When the new target is malformed or already
            monitored, or the new cron expression is empty.
    """
    with factory() as session:
        row = session.get(QualityMonitor, monitor_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        if target is not None:
            clean_target = validate_target(target)
            if clean_target != row.target:
                duplicate = session.scalar(
                    select(QualityMonitor.id).where(
                        QualityMonitor.workspace_id == workspace_id,
                        QualityMonitor.target == clean_target,
                    )
                )
                if duplicate is not None:
                    raise ValidationError(f"A monitor for {clean_target!r} already exists.")
                row.target = clean_target
        if cron_expr is not None:
            clean_cron = cron_expr.strip()
            if not clean_cron:
                raise ValidationError("cron_expr must not be empty.")
            row.cron_expr = clean_cron[:120]
        if is_active is not None:
            row.is_active = bool(is_active)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        _sync_backing_job(session, row)
        session.commit()
        session.refresh(row)
        counts = _open_anomaly_counts(session, [row.id])
        return serialize_monitor(row, open_anomalies=counts.get(row.id, 0))


def delete_monitor(factory: sessionmaker[Session], monitor_id: int, *, workspace_id: int) -> bool:
    """Delete a monitor, its snapshots, anomalies, and backing Job.

    Child rows are deleted explicitly (rather than relying on the FK
    cascade) because SQLite connections without the foreign-key
    pragma — the test engine among them — would otherwise orphan
    them silently.  The backing job's runs and log lines go with it.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: Primary key.
        workspace_id: Active workspace.

    Returns:
        ``True`` iff the monitor existed in the workspace.
    """
    with factory() as session:
        row = session.get(QualityMonitor, monitor_id)
        if row is None or row.workspace_id != workspace_id:
            return False
        session.execute(
            delete(TableProfileSnapshot).where(TableProfileSnapshot.monitor_id == monitor_id)
        )
        session.execute(delete(QualityAnomaly).where(QualityAnomaly.monitor_id == monitor_id))
        backing_id = row.backing_job_id
        session.delete(row)
        if backing_id is not None:
            run_ids = list(session.scalars(select(JobRun.id).where(JobRun.job_id == backing_id)))
            if run_ids:
                session.execute(delete(JobLog).where(JobLog.job_run_id.in_(run_ids)))
                session.execute(delete(JobRun).where(JobRun.id.in_(run_ids)))
            job = session.get(Job, backing_id)
            if job is not None:
                session.delete(job)
        session.commit()
        return True


def list_snapshots(
    factory: sessionmaker[Session],
    *,
    monitor_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return a monitor's most recent snapshots, newest first.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: Owning monitor.
        limit: Hard row cap.

    Returns:
        Serialised snapshot dicts.
    """
    with factory() as session:
        rows = session.scalars(
            select(TableProfileSnapshot)
            .where(TableProfileSnapshot.monitor_id == monitor_id)
            .order_by(desc(TableProfileSnapshot.captured_at), desc(TableProfileSnapshot.id))
            .limit(limit)
        ).all()
        return [serialize_snapshot(row) for row in rows]


def list_anomalies(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    monitor_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return anomalies for the workspace, newest-detected first.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace (joined through the monitor).
        monitor_id: Optional filter to one monitor.
        status: ``"open"`` (unresolved only), ``"resolved"``
            (resolved only), or ``None`` for both.
        limit: Hard row cap.

    Returns:
        Serialised anomaly dicts.
    """
    stmt = (
        select(QualityAnomaly)
        .join(QualityMonitor, QualityMonitor.id == QualityAnomaly.monitor_id)
        .where(QualityMonitor.workspace_id == workspace_id)
        .order_by(desc(QualityAnomaly.detected_at), desc(QualityAnomaly.id))
        .limit(limit)
    )
    if monitor_id is not None:
        stmt = stmt.where(QualityAnomaly.monitor_id == monitor_id)
    if status == "open":
        stmt = stmt.where(QualityAnomaly.resolved_at.is_(None))
    elif status == "resolved":
        stmt = stmt.where(QualityAnomaly.resolved_at.is_not(None))
    with factory() as session:
        rows = session.scalars(stmt).all()
        return [serialize_anomaly(row) for row in rows]
