# pyright: reportPrivateUsage=false
"""Top-level run orchestration: ``execute_run`` + core body + detach helper."""

from __future__ import annotations

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
from pointlessql.services.scheduler.runs._logic import dag_run_status, parse_config_json
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
    *,
    repair_of_run_id: int | None = None,
) -> JobRun:
    """Execute one run of *job_id* end-to-end and emit observability hooks.

    Thin wrapper around :func:`_execute_run_core` that also records
    Prometheus metrics, POSTs the optional failure webhook, and fans
    out the job's opt-in ``notify_on`` in-app notifications. Keeping
    this wrapper separate means tests can exercise the raw run logic
    without setting up a metrics registry or webhook stub, and also
    means the ``/api/jobs/{id}/run`` route goes through the same
    telemetry path as the scheduler loop.

    Args:
        factory: SQLAlchemy session factory for the PointlesSQL metadata DB.
        settings: Application settings (for ``for_principal``).
        registry: Kind → executor registry.
        job_id: Target job id.
        trigger: ``"scheduled"``, ``"manual"``, ``"event"``, or
            ``"repair"``.
        repair_of_run_id: For repair runs, the failed run whose
            succeeded DAG tasks should be reused instead of re-run.

    Returns:
        The final :class:`JobRun` row (post-commit, detached from the
        session so the caller can read attributes safely).
    """  # noqa: DOC502 — re-raised from _execute_run_core
    run = await _execute_run_core(
        factory, settings, registry, job_id, trigger, repair_of_run_id=repair_of_run_id
    )
    await _emit_run_telemetry(factory, job_id, run)
    _notify_run_outcome(factory, job_id, run)
    return run


async def _execute_run_core(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    job_id: int,
    trigger: str,
    *,
    repair_of_run_id: int | None = None,
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
        trigger: ``"scheduled"``, ``"manual"``, ``"event"``, or
            ``"repair"``.
        repair_of_run_id: For repair runs, the failed run whose
            succeeded DAG tasks should be reused instead of re-run
            (single-task jobs simply re-run).

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
        config, parse_err = parse_config_json(config_json)
        if parse_err is not None:
            with factory() as session:
                run = _start_run(session, job_id, trigger)
                _finish_run(
                    session,
                    run.id,
                    "failed",
                    f"invalid job config JSON: {parse_err}",
                )
                final = session.get(JobRun, run.id)
                assert final is not None
                session.expunge(final)
                return final

    satisfied_task_ids: set[int] | None = None
    if repair_of_run_id is not None and is_dag:
        from pointlessql.models import TaskRun

        with factory() as session:
            prev = list(
                session.scalars(select(TaskRun).where(TaskRun.job_run_id == repair_of_run_id)).all()
            )
        succeeded_ids = {tr.task_id for tr in prev if tr.status == "succeeded"}
        satisfied_task_ids = succeeded_ids & {t.id for t in tasks}

    with factory() as session:
        run = _start_run(session, job_id, trigger, repair_of_run_id=repair_of_run_id)
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
                ok, err = await _run_dag(
                    factory,
                    registry,
                    tasks,
                    run_id,
                    user_info,
                    uc_client,
                    satisfied_task_ids=satisfied_task_ids,
                )
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
                status, final_err = dag_run_status(ok, err)
                _finish_run(session, run_id, status, final_err)
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


def _notify_run_outcome(
    factory: sessionmaker[Session],
    job_id: int,
    run: JobRun,
) -> None:
    """Create the job's opt-in in-app notification for a finished run.

    Best-effort by design: notification delivery must never change a
    run's outcome, so every failure here is logged and swallowed.  The
    recipient is the run-as user (passed via ``extra_recipients`` with
    no actor, so the self-notification filter does not drop it).

    Args:
        factory: Session factory.
        job_id: The parent job (re-loaded for ``notify_on`` + name).
        run: The finished, detached run row.
    """
    if run.status not in ("succeeded", "failed"):
        return
    try:
        from pointlessql.services.notifications.fanout import fanout_event
        from pointlessql.services.scheduler.runs._logic import parse_notify_on

        with factory() as session:
            job = _load_job_by_id(session, job_id)
            if job is None:
                return
            wanted = parse_notify_on(job.notify_on)
            outcome = "failure" if run.status == "failed" else "success"
            if outcome not in wanted:
                return
            job_name = job.name
            recipient = job.run_as_user_id
            workspace_id = job.workspace_id
        suffix = f": {run.error}" if run.error else ""
        fanout_event(
            factory,
            event_type=f"pointlessql.job.run_{run.status}",
            entity_kind="job",
            entity_ref=str(job_id),
            workspace_id=workspace_id,
            actor_user_id=None,
            source_url=f"/jobs/{job_id}",
            summary_md=f"Job **{job_name}** run #{run.id} {run.status}{suffix}",
            extra_recipients=[recipient],
        )
    except Exception:  # noqa: BLE001 — notifications never fail a run
        logger.exception("scheduler: notify_on fan-out failed", extra={"job_id": job_id})
