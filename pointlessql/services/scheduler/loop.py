# pyright: reportPrivateUsage=false
"""Scheduler loop: ``tick_once`` + the :class:`Scheduler` driver class.

Owns the periodic ticker that polls every
:class:`~pointlessql.models.Job`, decides whether it is due, claims
a slot in the global + per-job semaphores, and dispatches into
:func:`pointlessql.services.scheduler.runs.execute_run`.
"""

from __future__ import annotations

import asyncio
import datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import Job, JobRun
from pointlessql.services import metrics as metrics_service
from pointlessql.services.scheduler.registry import KindRegistry, build_default_registry
from pointlessql.services.scheduler.runs import (
    _count_running_runs,
    _emit_run_telemetry,
    _insert_skipped,
    _is_due,
    _last_run_started,
    _utcnow,
    execute_run,
)
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)


async def tick_once(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    now: datetime.datetime | None = None,
    *,
    global_semaphore: asyncio.Semaphore | None = None,
    per_job_semaphores: dict[int, asyncio.Semaphore] | None = None,
) -> list[JobRun]:
    """Evaluate every job once and launch the due ones.

    Exposed as a top-level function so tests can call it directly with
    a frozen clock without standing up the long-running loop. The two
    semaphores are optional — when ``None`` the caller is telling us
    this tick does not need concurrency caps (tests typically go this
    route). When provided, the tick acquires the global semaphore
    before the per-job one to keep lock-ordering consistent.

    Args:
        factory: SQLAlchemy session factory.
        settings: Application settings.
        registry: Kind → executor registry.
        now: Override for the "current time" — defaults to real UTC now.
        global_semaphore: Cross-job concurrency cap.
        per_job_semaphores: Per-job concurrency caps, keyed by job id.

    Returns:
        Every :class:`JobRun` row written during this tick, in insert
        order. Includes ``skipped`` and ``failed`` outcomes so tests
        can assert on them without re-querying.
    """
    current_time = now or _utcnow()
    launched: list[JobRun] = []

    with factory() as session:
        jobs = list(session.scalars(select(Job)).all())

    for job in jobs:
        if job.is_paused:
            continue
        with factory() as session:
            last_started = _last_run_started(session, job.id)
            if not _is_due(job.cron_expr, current_time, last_started):
                continue
            running = _count_running_runs(session, job.id)
            if running >= max(1, job.max_parallel_runs):
                skipped = _insert_skipped(
                    session,
                    job.id,
                    reason="previous run still running",
                )
                session.expunge(skipped)
                launched.append(skipped)
                # Emit metrics for the synthetic skipped row too — it
                # never goes through ``execute_run`` so without this
                # the counter would miss every concurrency-saturated
                # tick.
                await _emit_run_telemetry(factory, job.id, skipped)
                continue
        run = await _execute_with_semaphores(
            factory,
            settings,
            registry,
            job.id,
            "scheduled",
            global_semaphore,
            per_job_semaphores,
        )
        launched.append(run)

    return launched


async def _execute_with_semaphores(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    job_id: int,
    trigger: str,
    global_sem: asyncio.Semaphore | None,
    per_job_sems: dict[int, asyncio.Semaphore] | None,
) -> JobRun:
    """Run :func:`execute_run` inside optional semaphore guards.

    Layered so that :func:`execute_run` itself stays free of
    concurrency concerns — tests call it directly and assert on
    outcomes without building any semaphores.
    """
    if global_sem is None and per_job_sems is None:
        return await execute_run(factory, settings, registry, job_id, trigger)

    per_job_sem: asyncio.Semaphore | None = None
    if per_job_sems is not None:
        per_job_sem = per_job_sems.get(job_id)
        if per_job_sem is None:
            # Resolve the per-job cap lazily from the row.
            with factory() as session:
                job = session.get(Job, job_id)
                limit = max(1, job.max_parallel_runs) if job else 1
            per_job_sem = asyncio.Semaphore(limit)
            per_job_sems[job_id] = per_job_sem

    async def _run() -> JobRun:
        return await execute_run(factory, settings, registry, job_id, trigger)

    if global_sem is not None and per_job_sem is not None:
        async with global_sem, per_job_sem:
            return await _run()
    if global_sem is not None:
        async with global_sem:
            return await _run()
    assert per_job_sem is not None
    async with per_job_sem:
        return await _run()


class Scheduler:
    """Long-running asyncio task that ticks every ``tick_seconds``.

    The scheduler is deliberately tiny: a single coroutine and two
    lifecycle methods. Integration happens in :func:`pointlessql.api.main._lifespan`
    which constructs one of these, calls :meth:`start`, and awaits
    :meth:`stop` on shutdown. Tests typically bypass the loop and call
    :func:`tick_once` / :func:`execute_run` directly.

    Args:
        factory: SQLAlchemy session factory.
        settings: Application settings.
        registry: Kind → executor registry. Defaults to
            :func:`build_default_registry`.
    """

    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        registry: KindRegistry | None = None,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._registry = registry or build_default_registry()
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._global_sem: asyncio.Semaphore | None = None
        self._per_job_sems: dict[int, asyncio.Semaphore] = {}

    def start(self) -> None:
        """Spawn the background tick task.

        Idempotent — a second call while a task is already running is
        a no-op, matching how ``_lifespan`` may be re-entered during
        uvicorn's ``--reload`` cycle.
        """
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._global_sem = asyncio.Semaphore(max(1, self._settings.scheduler.max_concurrent_runs))
        self._per_job_sems = {}
        self._task = asyncio.create_task(self._run(), name="pointlessql-scheduler")
        logger.info(
            "scheduler: started (tick=%ds, max_concurrent=%d)",
            self._settings.scheduler.tick_seconds,
            self._settings.scheduler.max_concurrent_runs,
        )

    async def stop(self) -> None:
        """Signal the loop to exit and await the task."""
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except TimeoutError:  # pragma: no cover — defensive
            self._task.cancel()
        logger.info("scheduler: stopped")
        self._task = None

    async def _run(self) -> None:
        """Tick forever until ``_stop_event`` fires.

        Each iteration swallows and logs any exception so a single bad
        job never crashes the loop. The ``asyncio.wait_for`` on the
        stop event gives us a clean shutdown without a polling sleep.

        On every iteration we also publish the observed tick lag — the
        difference between when this tick was *supposed* to fire
        (``previous_tick + tick_seconds``) and when it actually ran.
        A steadily growing gauge is the earliest signal that the loop
        is falling behind its cadence under load.
        """
        expected_next: float = asyncio.get_event_loop().time()
        tick_seconds = float(self._settings.scheduler.tick_seconds)
        while not self._stop_event.is_set():
            actual = asyncio.get_event_loop().time()
            metrics_service.observe_tick_lag(actual - expected_next)
            try:
                await tick_once(
                    self._factory,
                    self._settings,
                    self._registry,
                    global_semaphore=self._global_sem,
                    per_job_semaphores=self._per_job_sems,
                )
            except Exception:  # noqa: BLE001 — loop must survive any tick
                logger.exception("scheduler: tick failed")
            expected_next = actual + tick_seconds
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=tick_seconds,
                )
            except TimeoutError:
                continue
