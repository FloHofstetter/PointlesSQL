# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Per-task execution lifecycle — single-task and DAG walks."""

from __future__ import annotations

import datetime
import logging

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.config import task_id_var
from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.models import JobTask, TaskRun
from pointlessql.services.scheduler.dag import (
    _parse_depends_on,
    _topological_order,
    validate_dag,
)
from pointlessql.services.scheduler.registry import KindRegistry
from pointlessql.services.scheduler.runs._db import (
    _utcnow,
    _workspace_id_for_job_run,
    log_job,
)
from pointlessql.services.scheduler.runs._logic import (
    compose_task_fail_message,
    detect_upstream_failures,
    parse_config_json,
    retry_delay_seconds,
    select_max_attempts,
    upstream_skip_messages,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


def _create_task_run(
    session: Session,
    job_run_id: int,
    task_id: int,
    status: str,
) -> TaskRun:
    """Insert a :class:`TaskRun` row for one node in the DAG."""
    tr = TaskRun(
        workspace_id=_workspace_id_for_job_run(session, job_run_id),
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

    Sets :data:`~pointlessql.config.task_id_var` for the
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
        config, parse_err = parse_config_json(task.config)
        if parse_err is not None:
            detail = f"invalid task config JSON: {parse_err}"
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

        max_attempts = select_max_attempts(task.max_retries)
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
                # bare-broad-ok: error captured into last_error for retry loop
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
                delay = retry_delay_seconds(attempt, task.retry_backoff_seconds)
                if delay > 0:
                    # Look up via the runs package so tests that
                    # monkey-patch ``scheduler.runs._sleep`` are
                    # picked up at call time — a direct ``from . import
                    # _sleep`` would bind once at import time and
                    # silently bypass the patch.
                    from pointlessql.services.scheduler import runs as _runs_mod

                    await _runs_mod._sleep(delay)

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
        upstream_failed = detect_upstream_failures(deps, results)
        if upstream_failed:
            detail, task_error = upstream_skip_messages(t.name, upstream_failed)
            log_job(factory, job_run_id, t.id, "INFO", detail)
            with factory() as session:
                _update_task_run(
                    session,
                    task_run_ids[t.id],
                    status="skipped",
                    finished_at=_utcnow(),
                    error=task_error,
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
                run_error = compose_task_fail_message(t.name, err)

    return run_ok, run_error
