"""In-process cron-style scheduler for PointlesSQL jobs.

Sprint 19 introduces the minimum viable scheduler: an ``asyncio`` task
spawned by the FastAPI lifespan that wakes every
``scheduler_tick_seconds`` seconds, looks at every :class:`~pointlessql.models.Job`
row, and launches the ones whose ``cron_expr`` indicates they are due.
No APScheduler — it is overkill for a single-worker install and drags
in a SQLAlchemy-backed jobstore we do not need.

Key contracts:

* **Overlap prevention.** Before launching a job, the scheduler queries
  the DB for an outstanding ``running`` :class:`~pointlessql.models.JobRun`
  with the same ``job_id``. If one is found the tick inserts a
  ``skipped`` row instead of launching again. The DB is the single
  source of truth: an in-memory set would drift across process
  restarts and multiple workers (although we only deploy one).
* **Run-as-user.** Every job carries a ``run_as_user_id``. The scheduler
  loads the user and builds a :class:`~pointlessql.services.unitycatalog.UnityCatalogClient`
  via :meth:`~pointlessql.services.unitycatalog.UnityCatalogClient.for_principal`
  so ``X-Principal`` forwards to soyuz and soyuz's authorization
  rules apply exactly the way they do for HTTP-driven requests.
* **Executor registry.** A :class:`KindRegistry` maps ``kind`` → coroutine.
  Ships with ``"pg_sync"`` (wrapping :func:`pointlessql.services.pg_sync.run_sync`)
  and ``"python"`` (dispatches to a ``pointlessql.jobs`` entry point).
  Tests register fake kinds directly.
* **Correlation id.** The scheduler sets
  :data:`pointlessql.logging_config.request_id_var` to ``"job-<id>"``
  for the duration of each run so service-layer log lines emitted
  during the run carry a traceable id. Sprint 20 replaces this with
  a dedicated ``job_run_id_var`` once the DAG engine needs
  per-task correlation.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.metadata as _md
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.logging_config import request_id_var
from pointlessql.models import Job, JobRun, User
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


# Executor callable signature. ``uc_client`` is a ``UnityCatalogClient``
# built with ``for_principal(user.email)`` so soyuz's ``X-Principal``
# applies. ``config`` is the deserialized ``jobs.config`` dict. The
# executor returns ``None`` on success and raises on failure — the
# scheduler catches the exception, records it on the
# :class:`~pointlessql.models.JobRun`, and keeps ticking.
JobExecutor = Callable[
    [int, UserInfo, dict[str, Any], UnityCatalogClient],
    Awaitable[None],
]


class KindRegistry:
    """Mapping of ``kind`` identifier → executor coroutine.

    The registry is a plain object instead of a module-level ``dict``
    so tests can instantiate a fresh one per case without mutating
    shared state. The default registry populated by
    :func:`build_default_registry` seeds ``"pg_sync"`` and ``"python"``
    from this same module.
    """

    def __init__(self) -> None:
        self._executors: dict[str, JobExecutor] = {}

    def register(self, kind: str, executor: JobExecutor) -> None:
        """Register *executor* under *kind*, overwriting any previous entry."""
        self._executors[kind] = executor

    def get(self, kind: str) -> JobExecutor:
        """Return the executor for *kind*.

        Args:
            kind: Registry key.

        Returns:
            The executor coroutine.

        Raises:
            ValidationError: When *kind* has not been registered.
        """
        executor = self._executors.get(kind)
        if executor is None:
            raise ValidationError(f"Unknown job kind: {kind!r}")
        return executor


async def _pg_sync_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute the ``pg_sync`` kind by calling Sprint 18's ``run_sync``.

    Resolves the catalog's connection and (optional) credential through
    the principal-forwarded ``uc_client`` so the scheduler inherits the
    same authorization path the manual "Sync now" route uses.

    Args:
        job_run_id: Current run id (unused here but part of the
            :data:`JobExecutor` signature for symmetry with Sprint 20).
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``catalog_name``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``catalog_name`` is missing from config
            or the catalog is not a foreign catalog.
    """
    del job_run_id, user_info  # reserved for Sprint 20

    catalog_name = config.get("catalog_name")
    if not catalog_name:
        raise ValidationError(
            "pg_sync job config is missing required key 'catalog_name'"
        )

    from pointlessql.db import get_session_factory
    from pointlessql.services import pg_sync as pg_sync_service

    catalog = await uc_client.get_catalog(str(catalog_name))
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise ValidationError(
            f"pg_sync job target '{catalog_name}' is not a foreign catalog"
        )
    connection = await uc_client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = (
        options.get("credential_name") if isinstance(options, dict) else None
    )
    if credential_name:
        credential = await uc_client.get_credential(str(credential_name))

    factory = get_session_factory()
    await pg_sync_service.run_sync(
        uc=uc_client,
        factory=factory,
        catalog_name=str(catalog_name),
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )


async def _python_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute a user-authored job published via a ``pointlessql.jobs`` entry point.

    The ``entry_point`` key in ``config`` selects the entry-point name;
    the loaded object must be a coroutine with the
    :data:`JobExecutor` signature. This keeps plug-in authorship simple:
    ship a wheel that declares

    .. code-block:: toml

        [project.entry-points."pointlessql.jobs"]
        my_job = "my_pkg.jobs:run_my_job"

    and PointlesSQL discovers it without further configuration.

    Args:
        job_run_id: Current run id, forwarded to the plug-in.
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``entry_point``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``entry_point`` is missing or the entry
            point resolution fails.
    """
    entry_point_name = config.get("entry_point")
    if not entry_point_name:
        raise ValidationError(
            "python job config is missing required key 'entry_point'"
        )

    try:
        entries = _md.entry_points(group="pointlessql.jobs")
    except TypeError:  # pragma: no cover — very old importlib.metadata
        entries = _md.entry_points().get("pointlessql.jobs", [])  # type: ignore[attr-defined]

    matches = [ep for ep in entries if ep.name == entry_point_name]
    if not matches:
        raise ValidationError(
            f"python job entry point not found: {entry_point_name!r}"
        )

    fn = matches[0].load()
    await fn(job_run_id, user_info, config, uc_client)


def build_default_registry() -> KindRegistry:
    """Return a :class:`KindRegistry` with the built-in executors wired up.

    Returns:
        A fresh registry with ``"pg_sync"`` and ``"python"`` bound.
    """
    registry = KindRegistry()
    registry.register("pg_sync", _pg_sync_executor)
    registry.register("python", _python_executor)
    return registry


def _utcnow() -> datetime.datetime:
    """Return the current time in UTC — stubbable in tests."""
    return datetime.datetime.now(datetime.UTC)


def _load_job_by_id(session: Session, job_id: int) -> Job | None:
    """Return a :class:`Job` by id, or ``None``."""
    return session.get(Job, job_id)


def _has_running_run(session: Session, job_id: int) -> bool:
    """Return whether a ``running`` run already exists for *job_id*.

    The scheduler treats this as the authoritative overlap guard. We
    query on every tick rather than caching in memory because the
    source of truth is the DB and a worker restart must not lose the
    overlap fact.
    """
    stmt = (
        select(JobRun.id)
        .where(JobRun.job_id == job_id)
        .where(JobRun.status == "running")
        .limit(1)
    )
    return session.scalar(stmt) is not None


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


def _start_run(
    session: Session, job_id: int, trigger: str
) -> JobRun:
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


async def execute_run(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    job_id: int,
    trigger: str,
) -> JobRun:
    """Execute one run of *job_id* end-to-end.

    This is the core unit of work that both the scheduler loop and the
    manual "Run now" route invoke. It:

    1. Loads the job + run-as user.
    2. Inserts a ``running`` :class:`JobRun`, setting ``request_id_var``
       to ``job-<run_id>`` for the duration so downstream log lines
       carry a correlation id.
    3. Dispatches to the kind's executor with a principal-forwarded
       :class:`UnityCatalogClient`.
    4. Updates the run with a terminal status, re-raising
       :class:`PointlessSQLError` unchanged so the caller (the API
       route) can return a non-200 response.

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
        ValidationError: When the job or its run-as user cannot be
            resolved — the run is still recorded as ``failed`` before
            the exception propagates.
    """
    with factory() as session:
        job = _load_job_by_id(session, job_id)
        if job is None:
            raise ValidationError(f"Job {job_id} not found")
        user_info = _load_user_info(session, job.run_as_user_id)
        kind = job.kind
        config_json = job.config

    try:
        config: dict[str, Any] = json.loads(config_json or "{}")
    except json.JSONDecodeError as exc:
        # Malformed config is a permanent failure — record a failed run
        # so the UI surfaces it and move on.
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

    token = request_id_var.set(f"job-{run_id}")
    try:
        if user_info is None:
            message = (
                f"run-as user {job.run_as_user_id} is missing or inactive — "
                "cannot build principal client"
            )
            logger.error("scheduler: %s", message)
            with factory() as session:
                _finish_run(session, run_id, "failed", message)
            return _detached_run(factory, run_id)

        try:
            executor = registry.get(kind)
            uc_client = UnityCatalogClient.for_principal(
                settings, user_info["email"]
            )
            await executor(run_id, user_info, config, uc_client)
        except PointlessSQLError as exc:
            logger.warning(
                "scheduler: job %d (%s) failed: %s", job_id, kind, exc.detail
            )
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)
        except Exception as exc:  # noqa: BLE001 — scheduler must not crash
            logger.exception(
                "scheduler: job %d (%s) raised unexpectedly", job_id, kind
            )
            with factory() as session:
                _finish_run(session, run_id, "failed", str(exc))
            return _detached_run(factory, run_id)

        with factory() as session:
            _finish_run(session, run_id, "succeeded", None)
        return _detached_run(factory, run_id)
    finally:
        request_id_var.reset(token)


def _detached_run(
    factory: sessionmaker[Session], run_id: int
) -> JobRun:
    """Load a :class:`JobRun` and detach it for the caller."""
    with factory() as session:
        run = session.get(JobRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


async def tick_once(
    factory: sessionmaker[Session],
    settings: Settings,
    registry: KindRegistry,
    now: datetime.datetime | None = None,
) -> list[JobRun]:
    """Evaluate every job once and launch the due ones.

    Exposed as a top-level function so tests can call it directly with
    a frozen clock without standing up the long-running loop.

    Args:
        factory: SQLAlchemy session factory.
        settings: Application settings.
        registry: Kind → executor registry.
        now: Override for the "current time" — defaults to real UTC now.

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
            if _has_running_run(session, job.id):
                # Double-launch guard — write a skipped row so the UI
                # makes it clear the scheduler did notice the tick.
                skipped = _insert_skipped(
                    session,
                    job.id,
                    reason="previous run still running",
                )
                session.expunge(skipped)
                launched.append(skipped)
                continue
        # Launch outside the session context; execute_run manages its
        # own transactions.
        run = await execute_run(factory, settings, registry, job.id, "scheduled")
        launched.append(run)

    return launched


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

    def start(self) -> None:
        """Spawn the background tick task.

        Idempotent — a second call while a task is already running is
        a no-op, matching how ``_lifespan`` may be re-entered during
        uvicorn's ``--reload`` cycle.
        """
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="pointlessql-scheduler")
        logger.info(
            "scheduler: started (tick=%ds)",
            self._settings.scheduler_tick_seconds,
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
        """
        while not self._stop_event.is_set():
            try:
                await tick_once(self._factory, self._settings, self._registry)
            except Exception:  # noqa: BLE001 — loop must survive any tick
                logger.exception("scheduler: tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self._settings.scheduler_tick_seconds),
                )
            except TimeoutError:
                continue


__all__ = [
    "JobExecutor",
    "KindRegistry",
    "Scheduler",
    "build_default_registry",
    "execute_run",
    "tick_once",
]
