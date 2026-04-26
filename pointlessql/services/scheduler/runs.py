# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Job + task run lifecycle, structured logging, and failure-webhook telemetry.

Owns:

* DB helpers for the scheduler and loop modules
  (``_load_job_by_id``, ``_count_running_runs``, ``_last_run_started``,
  ``_is_due``, ``_load_user_info``, ``_start_run``, ``_insert_skipped``,
  ``_finish_run``, :func:`log_job`).
* Per-task execution lifecycle (``_create_task_run``,
  ``_update_task_run``, ``_run_one_task``, ``_run_dag``).
* Run orchestration (:func:`execute_run`, ``_execute_run_core``,
  ``_detached_run``, ``_emit_run_telemetry``,
  ``_post_failure_webhook``).
* Test-hook globals ``_sleep`` / ``_webhook_client_factory`` /
  ``_WEBHOOK_TIMEOUT_SECONDS`` — re-exported from the package
  ``__init__.py`` so tests can monkeypatch them via
  ``scheduler_service.runs._sleep``.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.logging_config import (
    job_run_id_var,
    request_id_var,
    task_id_var,
)
from pointlessql.models import (
    Job,
    JobLog,
    JobRun,
    JobTask,
    TaskRun,
    User,
)
from pointlessql.services import metrics as metrics_service
from pointlessql.services.scheduler.dag import (
    _parse_depends_on,
    _topological_order,
    validate_dag,
)
from pointlessql.services.scheduler.registry import KindRegistry
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


# Failure-webhook tuning.
#
# 5-second timeout: long enough to ride over a GC-pause or TLS
# handshake on a well-behaved receiver, short enough that a broken
# endpoint never wedges the scheduler. No retries — this is a
# best-effort notification, not a durable queue; the caller owns the
# canonical run state via the DB row.
_WEBHOOK_TIMEOUT_SECONDS: float = 5.0

# httpx client factory kept as a module-level callable so tests can
# monkeypatch it in place of a real network client. Any callable
# returning an object with ``post(url, json=..., timeout=...)`` works.
_WebhookClientFactory = Callable[[], httpx.AsyncClient]
_webhook_client_factory: _WebhookClientFactory = httpx.AsyncClient


# Injected for tests so retry backoff does not actually sleep.
_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


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
    if last_started is not None and last_started.tzinfo is None:
        last_started = last_started.replace(tzinfo=datetime.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)
    try:
        anchor = last_started or (now - datetime.timedelta(days=1))
        itr = croniter(cron_expr, anchor)
        next_fire = itr.get_next(datetime.datetime)
    except (ValueError, KeyError) as exc:
        raise ValidationError(f"Invalid cron expression: {cron_expr!r}") from exc
    # croniter returns a naive or aware datetime matching the anchor's
    # tz awareness. Our anchors are always UTC-aware so next_fire is too.
    if isinstance(next_fire, datetime.datetime):
        if next_fire.tzinfo is None:
            next_fire = next_fire.replace(tzinfo=datetime.UTC)
        return next_fire <= now
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
    )


def _start_run(session: Session, job_id: int, trigger: str) -> JobRun:
    """Insert a fresh ``running`` :class:`JobRun` and return it."""
    run = JobRun(
        job_id=job_id,
        started_at=_utcnow(),
        status="running",
        trigger=trigger,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _insert_skipped(session: Session, job_id: int, reason: str) -> JobRun:
    """Insert a ``skipped`` :class:`JobRun` with a trigger of ``scheduled``."""
    now = _utcnow()
    run = JobRun(
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
                job_run_id=job_run_id,
                task_id=task_id,
                ts=_utcnow(),
                level=level,
                message=message,
            )
        )
        session.commit()


# -- Task execution ---------------------------------------------------


def _create_task_run(
    session: Session,
    job_run_id: int,
    task_id: int,
    status: str,
) -> TaskRun:
    """Insert a :class:`TaskRun` row for one node in the DAG."""
    tr = TaskRun(
        job_run_id=job_run_id,
        task_id=task_id,
        status=status,
        attempts=0,
    )
    session.add(tr)
    session.commit()
    session.refresh(tr)
    return tr


def _update_task_run(
    session: Session,
    task_run_id: int,
    *,
    status: str | None = None,
    attempts: int | None = None,
    error: str | None = None,
    started_at: datetime.datetime | None = None,
    finished_at: datetime.datetime | None = None,
) -> None:
    """Mutate a :class:`TaskRun` — set only the provided fields."""
    row = session.get(TaskRun, task_run_id)
    if row is None:  # pragma: no cover — row was just inserted
        return
    if status is not None:
        row.status = status
    if attempts is not None:
        row.attempts = attempts
    if error is not None:
        row.error = error
    if started_at is not None:
        row.started_at = started_at
    if finished_at is not None:
        row.finished_at = finished_at
    session.commit()


async def _run_one_task(
    factory: sessionmaker[Session],
    registry: KindRegistry,
    task: JobTask,
    task_run_id: int,
    job_run_id: int,
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
) -> tuple[bool, str | None]:
    """Execute one task with retry support.

    Sets :data:`~pointlessql.logging_config.task_id_var` for the
    duration so log records emitted by the executor (including the
    :func:`log_job` rows this function writes) carry the task id.

    Args:
        factory: Session factory for writing state transitions.
        registry: Kind → executor registry.
        task: The :class:`JobTask` to run.
        task_run_id: Id of the pre-created :class:`TaskRun` row.
        job_run_id: Owning :class:`JobRun` id.
        user_info: Run-as user info, forwarded to the executor.
        uc_client: Principal-forwarded facade, forwarded to the executor.

    Returns:
        A ``(succeeded, error)`` tuple. ``succeeded`` is ``True`` iff
        *some* attempt succeeded; ``error`` is the final exception
        message when ``succeeded`` is ``False``.
    """
    task_token = task_id_var.set(str(task.id))
    try:
        try:
            config: dict[str, Any] = json.loads(task.config or "{}")
        except json.JSONDecodeError as exc:
            detail = f"invalid task config JSON: {exc}"
            log_job(factory, job_run_id, task.id, "ERROR", detail)
            with factory() as session:
                _update_task_run(
                    session,
                    task_run_id,
                    status="failed",
                    attempts=0,
                    error=detail,
                    finished_at=_utcnow(),
                )
            return False, detail

        try:
            executor = registry.get(task.kind)
        except ValidationError as exc:
            detail = exc.detail
            log_job(factory, job_run_id, task.id, "ERROR", detail)
            with factory() as session:
                _update_task_run(
                    session,
                    task_run_id,
                    status="failed",
                    attempts=0,
                    error=detail,
                    finished_at=_utcnow(),
                )
            return False, detail

        max_attempts = max(1, task.max_retries + 1)
        last_error: str | None = None
        started = _utcnow()
        log_job(
            factory,
            job_run_id,
            task.id,
            "INFO",
            f"task {task.name!r} starting (max_attempts={max_attempts})",
        )
        with factory() as session:
            _update_task_run(
                session,
                task_run_id,
                status="running",
                started_at=started,
            )

        for attempt in range(1, max_attempts + 1):
            try:
                await executor(job_run_id, user_info, config, uc_client)
            except PointlessSQLError as exc:
                last_error = exc.detail
            except Exception as exc:  # noqa: BLE001 — executor boundary
                last_error = str(exc)
            else:
                log_job(
                    factory,
                    job_run_id,
                    task.id,
                    "INFO",
                    f"task {task.name!r} succeeded on attempt {attempt}",
                )
                with factory() as session:
                    _update_task_run(
                        session,
                        task_run_id,
                        status="succeeded",
                        attempts=attempt,
                        finished_at=_utcnow(),
                    )
                return True, None

            # Failure path.
            log_job(
                factory,
                job_run_id,
                task.id,
                "WARNING",
                f"task {task.name!r} attempt {attempt}/{max_attempts} failed: {last_error}",
            )
            with factory() as session:
                _update_task_run(
                    session,
                    task_run_id,
                    attempts=attempt,
                    error=last_error,
                )
            if attempt < max_attempts:
                delay = float(attempt * task.retry_backoff_seconds)
                if delay > 0:
                    await _sleep(delay)

        log_job(
            factory,
            job_run_id,
            task.id,
            "ERROR",
            f"task {task.name!r} exhausted retries: {last_error}",
        )
        with factory() as session:
            _update_task_run(
                session,
                task_run_id,
                status="failed",
                finished_at=_utcnow(),
                error=last_error,
            )
        return False, last_error
    finally:
        task_id_var.reset(task_token)


async def _run_dag(
    factory: sessionmaker[Session],
    registry: KindRegistry,
    tasks: list[JobTask],
    job_run_id: int,
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
) -> tuple[bool, str | None]:
    """Walk *tasks* topologically, executing ready ones and skipping on upstream failure.

    Args:
        factory: Session factory for state transitions.
        registry: Kind → executor registry.
        tasks: Every :class:`JobTask` row in the job, pre-ordered (the
            function re-orders anyway; the caller pass is just the
            full set).
        job_run_id: Owning :class:`JobRun` id.
        user_info: Run-as user info.
        uc_client: Principal-forwarded facade.

    Returns:
        A ``(succeeded, error)`` tuple where ``succeeded`` is ``True``
        iff every task succeeded (any ``failed`` / ``skipped`` is a
        run-level failure).
    """
    validate_dag(tasks)
    ordered = _topological_order(tasks)
    task_run_ids: dict[int, int] = {}
    with factory() as session:
        for t in ordered:
            tr = _create_task_run(session, job_run_id, t.id, "pending")
            task_run_ids[t.id] = tr.id

    results: dict[int, str] = {}  # task.id -> "succeeded" | "failed" | "skipped"
    run_error: str | None = None
    run_ok = True

    for t in ordered:
        deps = _parse_depends_on(t.depends_on)
        upstream_failed = [d for d in deps if results.get(d) in {"failed", "skipped"}]
        if upstream_failed:
            detail = f"task {t.name!r} skipped: upstream {upstream_failed} did not succeed"
            log_job(factory, job_run_id, t.id, "INFO", detail)
            with factory() as session:
                _update_task_run(
                    session,
                    task_run_ids[t.id],
                    status="skipped",
                    finished_at=_utcnow(),
                    error=f"upstream {upstream_failed} failed",
                )
            results[t.id] = "skipped"
            run_ok = False
            run_error = run_error or detail
            continue

        ok, err = await _run_one_task(
            factory,
            registry,
            t,
            task_run_ids[t.id],
            job_run_id,
            user_info,
            uc_client,
        )
        if ok:
            results[t.id] = "succeeded"
        else:
            results[t.id] = "failed"
            run_ok = False
            if run_error is None:
                run_error = f"task {t.name!r} failed: {err}" if err else f"task {t.name!r} failed"

    return run_ok, run_error


async def execute_run(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    job_id: int,
    trigger: str,
) -> JobRun:
    """Execute one run of *job_id* end-to-end and emit observability hooks.

    Thin wrapper around :func:`_execute_run_core` that also records
    Prometheus metrics and POSTs the optional failure webhook. Keeping
    this wrapper separate means tests can exercise the raw run logic
    without setting up a metrics registry or webhook stub, and also
    means the ``/api/jobs/{id}/run`` route goes through the same
    telemetry path as the scheduler loop.

    Args:
        factory: SQLAlchemy session factory for the PointlesSQL metadata DB.
        settings: Application settings (for ``for_principal``).
        registry: Kind → executor registry.
        job_id: Target job id.
        trigger: ``"scheduled"`` or ``"manual"``.

    Returns:
        The final :class:`JobRun` row (post-commit, detached from the
        session so the caller can read attributes safely).
    """  # noqa: DOC502 — re-raised from _execute_run_core
    run = await _execute_run_core(factory, settings, registry, job_id, trigger)
    await _emit_run_telemetry(factory, job_id, run)
    return run


async def _execute_run_core(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    job_id: int,
    trigger: str,
) -> JobRun:
    """Execute one run of *job_id* end-to-end.

    This is the core unit of work that both the scheduler loop and the
    manual "Run now" route invoke via :func:`execute_run`. It:

    1. Loads the job + run-as user.
    2. Inserts a ``running`` :class:`JobRun`, setting
       :data:`~pointlessql.logging_config.job_run_id_var` and (for
       backwards compatibility with the single-task scheduler era)
       :data:`~pointlessql.logging_config.request_id_var` for the
       duration so downstream log lines carry correlation ids.
    3. If :class:`JobTask` rows exist, walks the DAG via :func:`_run_dag`.
       Otherwise falls back to the single-task shortcut.
    4. Updates the run with a terminal status.

    Args:
        factory: SQLAlchemy session factory for the PointlesSQL metadata DB.
        settings: Application settings (for ``for_principal``).
        registry: Kind → executor registry.
        job_id: Target job id.
        trigger: ``"scheduled"`` or ``"manual"``.

    Returns:
        The final :class:`JobRun` row (post-commit, detached from the
        session so the caller can read attributes safely).

    Raises:
        ValidationError: When the job cannot be resolved — the run is
            not inserted in that case so the caller observes the raise.
    """
    with factory() as session:
        job = _load_job_by_id(session, job_id)
        if job is None:
            raise ValidationError(f"Job {job_id} not found")
        user_info = _load_user_info(session, job.run_as_user_id)
        kind = job.kind
        config_json = job.config
        missing_user_run_as = job.run_as_user_id
        tasks = list(session.scalars(select(JobTask).where(JobTask.job_id == job_id)).all())
        for t in tasks:
            session.expunge(t)

    is_dag = len(tasks) > 0
    config: dict[str, Any] = {}

    if not is_dag:
        try:
            config = json.loads(config_json or "{}")
        except json.JSONDecodeError as exc:
            with factory() as session:
                run = _start_run(session, job_id, trigger)
                _finish_run(
                    session,
                    run.id,
                    "failed",
                    f"invalid job config JSON: {exc}",
                )
                final = session.get(JobRun, run.id)
                assert final is not None
                session.expunge(final)
                return final

    with factory() as session:
        run = _start_run(session, job_id, trigger)
        run_id = run.id

    req_token = request_id_var.set(f"job-{run_id}")
    job_token = job_run_id_var.set(str(run_id))
    try:
        if user_info is None:
            message = (
                f"run-as user {missing_user_run_as} is missing or inactive — "
                "cannot build principal client"
            )
            logger.error("scheduler: %s", message)
            log_job(factory, run_id, None, "ERROR", message)
            with factory() as session:
                _finish_run(session, run_id, "failed", message)
            return _detached_run(factory, run_id)

        try:
            uc_client = UnityCatalogClient.for_principal(settings, user_info["email"])
        except PointlessSQLError as exc:
            logger.warning("scheduler: job %d principal client failed: %s", job_id, exc.detail)
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)

        if is_dag:
            try:
                ok, err = await _run_dag(factory, registry, tasks, run_id, user_info, uc_client)
            except ValidationError as exc:
                logger.warning("scheduler: job %d DAG invalid: %s", job_id, exc.detail)
                log_job(factory, run_id, None, "ERROR", exc.detail)
                with factory() as session:
                    _finish_run(session, run_id, "failed", exc.detail)
                return _detached_run(factory, run_id)
            with factory() as session:
                _finish_run(
                    session,
                    run_id,
                    "succeeded" if ok else "failed",
                    None if ok else err,
                )
            return _detached_run(factory, run_id)

        # Single-task shortcut.
        try:
            executor = registry.get(kind)
            log_job(
                factory,
                run_id,
                None,
                "INFO",
                f"single-task job kind={kind} starting",
            )
            await executor(run_id, user_info, config, uc_client)
        except PointlessSQLError as exc:
            logger.warning("scheduler: job %d (%s) failed: %s", job_id, kind, exc.detail)
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)
        except Exception as exc:  # noqa: BLE001 — scheduler must not crash
            logger.exception("scheduler: job %d (%s) raised unexpectedly", job_id, kind)
            log_job(factory, run_id, None, "ERROR", str(exc))
            with factory() as session:
                _finish_run(session, run_id, "failed", str(exc))
            return _detached_run(factory, run_id)

        log_job(factory, run_id, None, "INFO", "job succeeded")
        with factory() as session:
            _finish_run(session, run_id, "succeeded", None)
        return _detached_run(factory, run_id)
    finally:
        job_run_id_var.reset(job_token)
        request_id_var.reset(req_token)


def _detached_run(factory: sessionmaker[Session], run_id: int) -> JobRun:
    """Load a :class:`JobRun` and detach it for the caller."""
    with factory() as session:
        run = session.get(JobRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


def _duration_seconds(run: JobRun) -> float | None:
    """Return ``finished_at - started_at`` as seconds, or ``None``.

    Synthetic ``skipped`` rows share a single timestamp so the
    difference is exactly ``0.0``; we still return that as a valid
    observation so dashboards see the skip in the duration histogram's
    smallest bucket. ``None`` is only returned when ``finished_at`` is
    still missing (running or uninitialised row) — the schema makes
    ``started_at`` non-nullable so it can be taken at face value.
    """
    if run.finished_at is None:
        return None
    started = run.started_at
    finished = run.finished_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=datetime.UTC)
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=datetime.UTC)
    return (finished - started).total_seconds()


def _load_job_name_and_webhook(
    factory: sessionmaker[Session], job_id: int
) -> tuple[str, str | None]:
    """Snapshot ``(name, on_failure_url)`` for *job_id*.

    Kept separate from the main :func:`execute_run` body so the webhook
    dispatcher does not re-hit the DB for every failure path. Returns
    ``("", None)`` when the job row has disappeared (race with a
    concurrent delete), which means the caller emits metrics with an
    empty ``job_name`` label and skips the webhook.
    """
    with factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return "", None
        return job.name, job.on_failure_url


async def _post_failure_webhook(
    url: str,
    payload: dict[str, Any],
) -> None:
    """POST *payload* to *url*, logging and swallowing any failure.

    The webhook is advisory — a receiver being down, slow, or
    misconfigured must never affect the scheduler's own bookkeeping.
    :data:`_WEBHOOK_TIMEOUT_SECONDS` caps the wait so a stalled
    receiver cannot wedge the scheduler loop. Uses the module-level
    :data:`_webhook_client_factory` so tests can swap in a stub.

    Args:
        url: Opt-in endpoint taken from :attr:`pointlessql.models.Job.on_failure_url`.
        payload: JSON body — timestamps are pre-serialised ISO-8601
            strings by the caller so this function is oblivious to
            the run's internal datetime representation.
    """
    try:
        async with _webhook_client_factory() as client:
            await client.post(url, json=payload, timeout=_WEBHOOK_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        logger.warning("scheduler: on_failure_url webhook to %s failed: %s", url, exc)
    except Exception as exc:  # noqa: BLE001 — webhook boundary
        logger.warning(
            "scheduler: on_failure_url webhook to %s raised %s: %s",
            url,
            type(exc).__name__,
            exc,
        )


async def _emit_run_telemetry(
    factory: sessionmaker[Session],
    job_id: int,
    run: JobRun,
) -> None:
    """Emit Prometheus metrics + the optional failure webhook for *run*.

    Single bookkeeping path so every call site through
    :func:`execute_run` and :func:`tick_once` shares the same rules —
    there is no code path where a terminal state is written but the
    metrics/webhook are missed.

    Args:
        factory: Session factory for the job-name + URL snapshot.
        job_id: Parent job id (passed in so we don't rely on the
            detached run still knowing its owning row).
        run: Detached terminal :class:`JobRun`.
    """
    job_name, on_failure_url = _load_job_name_and_webhook(factory, job_id)
    duration = _duration_seconds(run)
    metrics_service.record_run(job_name, run.status, duration)

    if run.status != "failed" or not on_failure_url:
        return

    payload: dict[str, Any] = {
        "job_id": job_id,
        "job_name": job_name,
        "run_id": run.id,
        "status": run.status,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    await _post_failure_webhook(on_failure_url, payload)
