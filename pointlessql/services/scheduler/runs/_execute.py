# pyright: reportPrivateUsage=false
"""Top-level run orchestration: ``execute_run`` + core body + detach helper."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.config import (
    Settings,
    job_run_id_var,
    request_id_var,
)
from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.models import JobRun, JobTask
from pointlessql.services.scheduler.registry import KindRegistry
from pointlessql.services.scheduler.runs._db import (
    _finish_run,
    _load_job_by_id,
    _load_user_info,
    _start_run,
    log_job,
)
from pointlessql.services.scheduler.runs._tasks import _run_dag
from pointlessql.services.scheduler.runs._telemetry import _emit_run_telemetry
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)


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
       :data:`~pointlessql.config.job_run_id_var` and (for
       backwards compatibility with the single-task scheduler era)
       :data:`~pointlessql.config.request_id_var` for the
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
            logger.warning(
                "scheduler: principal client failed: %s",
                exc.detail,
                extra={"job_id": job_id, "run_id": run_id},
            )
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)

        if is_dag:
            try:
                ok, err = await _run_dag(factory, registry, tasks, run_id, user_info, uc_client)
            except ValidationError as exc:
                logger.warning(
                    "scheduler: DAG invalid: %s",
                    exc.detail,
                    extra={"job_id": job_id, "run_id": run_id},
                )
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
            logger.warning(
                "scheduler: single-task job failed: %s",
                exc.detail,
                extra={"job_id": job_id, "run_id": run_id, "kind": kind},
            )
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)
        except Exception as exc:  # noqa: BLE001 — scheduler must not crash
            logger.exception(
                "scheduler: single-task job raised unexpectedly",
                extra={"job_id": job_id, "run_id": run_id, "kind": kind},
            )
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
