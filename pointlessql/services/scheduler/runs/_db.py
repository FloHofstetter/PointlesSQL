# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""DB helpers shared between the scheduler loop and run-execution paths.

Every helper here is sync — the scheduler calls them from coroutines via
direct invocation since the underlying SQLAlchemy session is sync.
"""

from __future__ import annotations

import datetime
import logging

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import Job, JobLog, JobRun, User
from pointlessql.services.scheduler.runs._logic import ensure_utc
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


def _utcnow() -> datetime.datetime:
    """Return the current time in UTC — stubbable in tests."""
    return datetime.datetime.now(datetime.UTC)


def _load_job_by_id(session: Session, job_id: int) -> Job | None:
    """Return a :class:`Job` by id, or ``None``."""
    return session.get(Job, job_id)


def _count_running_runs(session: Session, job_id: int) -> int:
    """Return the number of runs currently in ``running`` for *job_id*."""
    stmt = select(JobRun.id).where(JobRun.job_id == job_id).where(JobRun.status == "running")
    return len(list(session.scalars(stmt).all()))


def _last_run_started(session: Session, job_id: int) -> datetime.datetime | None:
    """Return the ``started_at`` of the most recent :class:`JobRun`.

    Used to decide whether the next cron occurrence since the previous
    tick has actually elapsed — the scheduler compares against ``now``
    to avoid launching the job twice in rapid ticks.
    """
    stmt = (
        select(JobRun.started_at)
        .where(JobRun.job_id == job_id)
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def _is_due(
    cron_expr: str,
    now: datetime.datetime,
    last_started: datetime.datetime | None,
) -> bool:
    """Return ``True`` when *cron_expr* indicates the job should run now.

    A job is due when its next-occurrence relative to the previous run
    (or epoch for a never-run job) is less than or equal to ``now``.
    Using ``croniter`` with the previous start as anchor handles the
    "tick interval larger than one cron minute" case cleanly — missed
    firings collapse to a single run rather than queueing up.

    Args:
        cron_expr: 5-field cron expression.
        now: Current timestamp.
        last_started: ``started_at`` of the most recent run, or ``None``
            when the job has never run.

    Returns:
        Whether the job should be launched this tick.

    Raises:
        ValidationError: When *cron_expr* fails to parse.
    """
    # SQLite strips tzinfo on DateTime roundtrip even when the column is
    # ``DateTime(timezone=True)`` — the DB dialect treats it as a display
    # hint only. Normalise any naive timestamp read back from the DB to
    # UTC-aware so ``croniter`` and the comparison below work uniformly
    # across SQLite and Postgres.
    if last_started is not None:
        last_started = ensure_utc(last_started)
    now = ensure_utc(now)
    try:
        anchor = last_started or (now - datetime.timedelta(days=1))
        itr = croniter(cron_expr, anchor)
        next_fire = itr.get_next(datetime.datetime)
    except (ValueError, KeyError) as exc:
        raise ValidationError(f"Invalid cron expression: {cron_expr!r}") from exc
    # croniter returns a naive or aware datetime matching the anchor's
    # tz awareness. Our anchors are always UTC-aware so next_fire is too.
    if isinstance(next_fire, datetime.datetime):
        return ensure_utc(next_fire) <= now
    return False  # pragma: no cover — croniter always returns datetime


def _load_user_info(session: Session, user_id: int) -> UserInfo | None:
    """Return a :class:`UserInfo` for *user_id*, or ``None`` when missing."""
    user = session.get(User, user_id)
    if user is None:
        return None
    return UserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_supervisor=bool(user.is_supervisor),
        is_auditor=bool(user.is_auditor),
    )


def _workspace_id_for_job(session: Session, job_id: int) -> int:
    """Return the parent job's workspace_id, or 1 on miss.

    JobRun rows denormalise their workspace from the parent Job
    so the runs-list page can filter without a JOIN.
    """
    from pointlessql.models import Job as _Job

    value = session.scalar(select(_Job.workspace_id).where(_Job.id == job_id))
    return int(value) if value is not None else 1


def _start_run(
    session: Session,
    job_id: int,
    trigger: str,
    repair_of_run_id: int | None = None,
) -> JobRun:
    """Insert a fresh ``running`` :class:`JobRun` and return it."""
    run = JobRun(
        workspace_id=_workspace_id_for_job(session, job_id),
        job_id=job_id,
        started_at=_utcnow(),
        status="running",
        trigger=trigger,
        repair_of_run_id=repair_of_run_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _insert_skipped(session: Session, job_id: int, reason: str) -> JobRun:
    """Insert a ``skipped`` :class:`JobRun` with a trigger of ``scheduled``."""
    now = _utcnow()
    run = JobRun(
        workspace_id=_workspace_id_for_job(session, job_id),
        job_id=job_id,
        started_at=now,
        finished_at=now,
        status="skipped",
        trigger="scheduled",
        error=reason,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _finish_run(
    session: Session,
    run_id: int,
    status: str,
    error: str | None,
) -> None:
    """Flip a :class:`JobRun` from ``running`` to its terminal status."""
    run = session.get(JobRun, run_id)
    if run is None:  # pragma: no cover — the row was just inserted
        return
    run.status = status
    run.finished_at = _utcnow()
    run.error = error
    session.commit()


def _workspace_id_for_job_run(session: Session, job_run_id: int) -> int:
    """Return the parent JobRun's workspace_id, or 1 on miss."""
    value = session.scalar(select(JobRun.workspace_id).where(JobRun.id == job_run_id))
    return int(value) if value is not None else 1


def log_job(
    factory: sessionmaker[Session],
    job_run_id: int,
    task_id: int | None,
    level: str,
    message: str,
) -> None:
    """Append one :class:`~pointlessql.models.JobLog` row.

    Synchronous on purpose — the scheduler calls this at every task
    state transition and we want the log rows to be visible in the
    next HTTP request for the log panel without waiting on any
    background flush. SQLite's ``Text`` write is cheap enough that this
    does not gate throughput.

    Args:
        factory: SQLAlchemy session factory for the PointlesSQL metadata DB.
        job_run_id: Owning :class:`~pointlessql.models.JobRun` id.
        task_id: Owning :class:`~pointlessql.models.JobTask` id, or
            ``None`` for run-scoped lifecycle events.
        level: Python log level name (``"INFO"``, ``"WARNING"``,
            ``"ERROR"``).
        message: Free-form log text.
    """
    with factory() as session:
        session.add(
            JobLog(
                workspace_id=_workspace_id_for_job_run(session, job_run_id),
                job_run_id=job_run_id,
                task_id=task_id,
                ts=_utcnow(),
                level=level,
                message=message,
            )
        )
        session.commit()
