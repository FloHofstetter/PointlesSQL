"""In-process cron-style scheduler with multi-task DAG execution.

Sprint 19 shipped the minimum viable scheduler — one task per job,
launched when the cron expression fired. Sprint 20 extends that with:

* **Multi-task DAGs.** Each job can have many :class:`~pointlessql.models.JobTask`
  rows wired into a directed acyclic graph via ``depends_on``. The
  scheduler walks the graph in topological order, launches ready
  tasks (ones whose upstreams have all succeeded), and marks downstream
  tasks ``skipped`` when any upstream fails.
* **Per-task retries.** Each task carries ``max_retries`` and
  ``retry_backoff_seconds``. Retries are linear (``attempt_index *
  backoff``) because every attempt already competes for the per-job
  and global scheduler semaphores — exponential on top just makes
  tuning harder.
* **Structured logging.** Every state transition (start, retry,
  success, failure, skip) writes a :class:`~pointlessql.models.JobLog`
  row via :func:`log_job`, and the scheduler per-task span sets
  :data:`~pointlessql.logging_config.job_run_id_var`,
  :data:`~pointlessql.logging_config.task_id_var`, and (for backwards
  compatibility with Sprint 19 log lines) :data:`~pointlessql.logging_config.request_id_var`
  so stdlib logger output carries the same correlation ids.
* **Concurrency caps.** A global
  :class:`asyncio.Semaphore` built from
  :attr:`~pointlessql.settings.Settings.scheduler_max_concurrent_runs`
  limits the total number of in-flight runs; a per-job semaphore
  (``max_parallel_runs``) limits fan-out for a single job. Both
  semaphores are acquired *before* the :class:`JobRun` flips to
  ``running`` so queued runs do not hold DB state.
* **Cycle detection.** Cycles in a DAG raise
  :class:`~pointlessql.exceptions.ValidationError` at creation time via
  :func:`validate_dag`. Implemented as a DFS three-color walk (WHITE →
  GRAY → BLACK): a back-edge onto a GRAY node is a cycle.

Jobs with *no* :class:`JobTask` rows fall back to the Sprint 19
single-task shortcut and invoke the executor registered under
``job.kind`` with ``job.config`` as its payload.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.metadata as _md
import json
import logging
import os
import threading
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

import httpx
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import EngineError, PointlessSQLError, ValidationError
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


# Executor callable signature. ``uc_client`` is a ``UnityCatalogClient``
# built with ``for_principal(user.email)`` so soyuz's ``X-Principal``
# applies. ``config`` is the deserialized ``jobs.config`` (single-task
# shortcut) or ``job_tasks.config`` (DAG task) dict. The executor
# returns ``None`` on success and raises on failure — the scheduler
# catches the exception, records it on the
# :class:`~pointlessql.models.JobRun` / :class:`~pointlessql.models.TaskRun`,
# and keeps ticking.
JobExecutor = Callable[
    [int, UserInfo, dict[str, Any], UnityCatalogClient],
    Awaitable[None],
]


# Injected for tests so retry backoff does not actually sleep.
_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


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


# Papermill drives kernel subprocesses that inherit the parent's
# ``os.environ``. Concurrent executions would otherwise race on the
# ``POINTLESSQL_PRINCIPAL`` slot when set through ``os.environ``; this
# lock serialises the narrow window between "set env" and "spawn kernel"
# without blocking the rest of the scheduler loop. Cell execution itself
# runs outside the lock.
_papermill_env_lock = threading.Lock()


def _resolve_notebook_path(notebooks_dir: Path, notebook_path: str) -> Path:
    """Resolve *notebook_path* under *notebooks_dir*, rejecting traversal.

    Args:
        notebooks_dir: Absolute root directory the notebook must live under.
        notebook_path: Relative path supplied in the job config.

    Returns:
        The resolved absolute path to the input notebook.

    Raises:
        ValidationError: When *notebook_path* is absolute, empty, escapes
            *notebooks_dir*, or does not point at an existing file.
    """
    if not notebook_path:
        raise ValidationError(
            "papermill job config 'notebook_path' must be a non-empty string"
        )
    candidate = Path(notebook_path)
    if candidate.is_absolute():
        raise ValidationError(
            f"papermill notebook_path must be relative to the notebooks "
            f"directory: {notebook_path!r}"
        )
    resolved = (notebooks_dir / candidate).resolve()
    try:
        resolved.relative_to(notebooks_dir)
    except ValueError as exc:
        raise ValidationError(
            f"papermill notebook_path {notebook_path!r} escapes the "
            f"notebooks directory"
        ) from exc
    if not resolved.is_file():
        raise ValidationError(
            f"papermill notebook not found: {notebook_path!r}"
        )
    return resolved


def _run_papermill_blocking(
    input_path: Path,
    output_path: Path,
    parameters: dict[str, Any],
    cwd: Path,
    principal: str,
    execution_timeout: int,
) -> None:
    """Invoke ``papermill.execute_notebook`` synchronously.

    Runs inside an ``asyncio.to_thread`` worker. Sets
    ``POINTLESSQL_PRINCIPAL`` on ``os.environ`` under a module-level
    lock so the spawned Jupyter kernel inherits the run-as user's
    email for :class:`~pointlessql.pql.PQL` to pick up.
    """
    import papermill  # type: ignore[import-untyped]
    from papermill.exceptions import (  # type: ignore[import-untyped]
        PapermillExecutionError,
    )

    with _papermill_env_lock:
        previous = os.environ.get("POINTLESSQL_PRINCIPAL")
        os.environ["POINTLESSQL_PRINCIPAL"] = principal
        try:
            try:
                papermill.execute_notebook(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    parameters=parameters,
                    kernel_name="python3",
                    cwd=str(cwd),
                    execution_timeout=execution_timeout,
                    progress_bar=False,
                )
            except PapermillExecutionError as exc:
                raise EngineError(
                    f"papermill execution failed in cell {exc.exec_count}: "
                    f"{exc.ename}: {exc.evalue}"
                ) from exc
        finally:
            if previous is None:
                os.environ.pop("POINTLESSQL_PRINCIPAL", None)
            else:
                os.environ["POINTLESSQL_PRINCIPAL"] = previous


async def _papermill_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Execute a notebook via Papermill, writing the result under ``runs/``.

    Config shape:

    .. code-block:: json

        {
            "notebook_path": "pipelines/etl.ipynb",
            "parameters": {"date": "2026-04-17"},
            "timeout_seconds": 600
        }

    ``notebook_path`` is resolved relative to ``settings.notebooks_dir``
    and must not escape it. The executed output lands at
    ``{notebooks_dir}/runs/{job_run_id}.ipynb`` so the embedded
    JupyterLab can serve it at ``/lab/tree/runs/{job_run_id}.ipynb``
    (the job-detail page links straight to that URL). ``timeout_seconds``
    is forwarded to papermill's per-cell ``execution_timeout`` and also
    backstopped by an ``asyncio.wait_for`` around the blocking call.

    The run-as user's email is exported as ``POINTLESSQL_PRINCIPAL`` in
    the Jupyter kernel subprocess so any :class:`~pointlessql.pql.PQL`
    instance constructed inside the notebook inherits the same
    principal forwarding the scheduler applies to its own
    ``uc_client``.

    Args:
        job_run_id: Current run id — used as the output filename.
        user_info: The run-as user's :class:`UserInfo` — ``email`` is
            exported as ``POINTLESSQL_PRINCIPAL`` for the kernel.
        config: Must carry ``notebook_path``. ``parameters`` and
            ``timeout_seconds`` are optional.
        uc_client: Principal-forwarded facade. Not used directly by the
            executor (notebook code constructs its own :class:`PQL`)
            but kept in the signature for symmetry with the other
            built-in kinds.

    Raises:
        ValidationError: When ``notebook_path`` is missing, not a
            string, escapes ``notebooks_dir``, or does not exist; or
            when ``parameters`` / ``timeout_seconds`` have the wrong
            type.
        EngineError: When the notebook raises during execution, when
            the execution exceeds the timeout, or when papermill
            itself errors out.
    """
    del uc_client  # kernel subprocess builds its own PQL client

    notebook_path = config.get("notebook_path")
    if not isinstance(notebook_path, str):
        raise ValidationError(
            "papermill job config is missing required key 'notebook_path'"
        )

    parameters = config.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValidationError(
            "papermill job config 'parameters' must be an object"
        )

    settings = Settings()
    timeout_cfg = config.get("timeout_seconds")
    if timeout_cfg is None:
        timeout_seconds = settings.notebook_execute_timeout_seconds
    elif isinstance(timeout_cfg, int) and timeout_cfg > 0:
        timeout_seconds = timeout_cfg
    else:
        raise ValidationError(
            "papermill job config 'timeout_seconds' must be a positive int"
        )

    notebooks_dir = Path(settings.notebooks_dir).resolve()
    input_path = _resolve_notebook_path(notebooks_dir, notebook_path)
    runs_dir = notebooks_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{job_run_id}.ipynb"

    principal = user_info["email"]
    logger.info(
        "papermill: executing %s → %s (timeout=%ds, principal=%s)",
        input_path,
        output_path,
        timeout_seconds,
        principal,
    )

    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                _run_papermill_blocking,
                input_path,
                output_path,
                dict(parameters),
                notebooks_dir,
                principal,
                timeout_seconds,
            ),
            timeout=timeout_seconds + 5,
        )
    except TimeoutError as exc:
        raise EngineError(
            f"papermill execution timed out after {timeout_seconds}s"
        ) from exc

    logger.info("papermill: finished %s", output_path)


def build_default_registry() -> KindRegistry:
    """Return a :class:`KindRegistry` with the built-in executors wired up.

    Returns:
        A fresh registry with ``"pg_sync"``, ``"python"``, and
        ``"papermill"`` bound.
    """
    registry = KindRegistry()
    registry.register("pg_sync", _pg_sync_executor)
    registry.register("python", _python_executor)
    registry.register("papermill", _papermill_executor)
    return registry


def _utcnow() -> datetime.datetime:
    """Return the current time in UTC — stubbable in tests."""
    return datetime.datetime.now(datetime.UTC)


def _load_job_by_id(session: Session, job_id: int) -> Job | None:
    """Return a :class:`Job` by id, or ``None``."""
    return session.get(Job, job_id)


def _count_running_runs(session: Session, job_id: int) -> int:
    """Return the number of runs currently in ``running`` for *job_id*."""
    stmt = (
        select(JobRun.id)
        .where(JobRun.job_id == job_id)
        .where(JobRun.status == "running")
    )
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


# -- DAG primitives ---------------------------------------------------


def _parse_depends_on(raw: str) -> list[int]:
    """Deserialize a ``job_tasks.depends_on`` string into a list of ids."""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"task depends_on is not valid JSON: {raw!r}"
        ) from exc
    if not isinstance(value, list):
        raise ValidationError("task depends_on must be a JSON array")
    typed: list[int] = []
    for item in value:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, int):
            raise ValidationError(
                "task depends_on entries must be integers"
            )
        typed.append(item)
    return typed


def validate_dag(tasks: Iterable[JobTask]) -> None:
    """Ensure the task graph is a DAG.

    Iterative three-color DFS: nodes start WHITE. When we descend into
    a node we mark it GRAY; when we come back up we mark it BLACK. A
    back-edge onto a GRAY node means we've looped back into the
    current recursion stack — that is a cycle. BLACK nodes are fully
    explored and safe to cross repeatedly. Also checks every
    ``depends_on`` target actually exists within the same job.

    Args:
        tasks: All :class:`JobTask` rows that form the candidate DAG.

    Raises:
        ValidationError: When any cycle is detected or a dependency
            points to an id outside the supplied set.
    """
    task_list = list(tasks)
    by_id: dict[int, JobTask] = {t.id: t for t in task_list}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {t.id: WHITE for t in task_list}

    # Pre-resolve every task's dependency list once so the walk below
    # is a pure graph traversal with no further JSON parsing.
    deps_of: dict[int, list[int]] = {}
    for t in task_list:
        parsed = _parse_depends_on(t.depends_on)
        for dep_id in parsed:
            if dep_id not in by_id:
                raise ValidationError(
                    f"task {t.id} depends on unknown task id {dep_id}"
                )
        deps_of[t.id] = parsed

    for root in task_list:
        if color[root.id] != WHITE:
            continue
        # Stack frames: (task_id, remaining-deps-to-visit). Fresh
        # frames push a copy of ``deps_of[node]`` so we can pop from
        # it without mutating the shared map.
        path: list[int] = [root.id]
        stack: list[tuple[int, list[int]]] = [
            (root.id, list(deps_of[root.id]))
        ]
        color[root.id] = GRAY
        while stack:
            node_id, remaining = stack[-1]
            if not remaining:
                color[node_id] = BLACK
                path.pop()
                stack.pop()
                continue
            next_dep = remaining.pop(0)
            state = color[next_dep]
            if state == GRAY:
                cycle = path[path.index(next_dep):] + [next_dep]
                raise ValidationError(
                    f"cycle detected in task graph: {cycle}"
                )
            if state == BLACK:
                continue
            color[next_dep] = GRAY
            path.append(next_dep)
            stack.append((next_dep, list(deps_of[next_dep])))


def _topological_order(tasks: list[JobTask]) -> list[JobTask]:
    """Return *tasks* in a deterministic topological order.

    Kahn's algorithm walks the graph breadth-first: start with every
    node that has no unsatisfied dependencies, emit it, decrement the
    remaining-count of its dependents, and repeat. Within each "round"
    we sort by ``id`` so the order is stable across runs — tests rely
    on this for round-by-round assertions.

    Args:
        tasks: All :class:`JobTask` rows for one job.

    Returns:
        The same rows, re-ordered so every task appears after its
        dependencies.

    Raises:
        ValidationError: When the graph contains a cycle (should have
            been caught at DAG-validation time, but we guard here too).
    """
    by_id: dict[int, JobTask] = {t.id: t for t in tasks}
    deps: dict[int, list[int]] = {t.id: _parse_depends_on(t.depends_on) for t in tasks}
    remaining: dict[int, int] = {tid: len(d) for tid, d in deps.items()}
    # Reverse map: dep_id → list of tasks that depend on it.
    dependents: dict[int, list[int]] = {tid: [] for tid in by_id}
    for tid, d in deps.items():
        for dep_id in d:
            dependents[dep_id].append(tid)

    ready = sorted(tid for tid, n in remaining.items() if n == 0)
    output: list[JobTask] = []
    while ready:
        tid = ready.pop(0)
        output.append(by_id[tid])
        for child in sorted(dependents[tid]):
            remaining[child] -= 1
            if remaining[child] == 0:
                # Insert in sorted position so the stable order holds.
                ready.append(child)
                ready.sort()
    if len(output) != len(tasks):
        raise ValidationError("cycle detected in task graph during toposort")
    return output


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
                f"task {task.name!r} attempt {attempt}/{max_attempts} "
                f"failed: {last_error}",
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
        upstream_failed = [
            d for d in deps if results.get(d) in {"failed", "skipped"}
        ]
        if upstream_failed:
            detail = (
                f"task {t.name!r} skipped: upstream "
                f"{upstream_failed} did not succeed"
            )
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
                run_error = (
                    f"task {t.name!r} failed: {err}" if err else
                    f"task {t.name!r} failed"
                )

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
       Sprint 19 compatibility) :data:`~pointlessql.logging_config.request_id_var`
       for the duration so downstream log lines carry correlation ids.
    3. If :class:`JobTask` rows exist, walks the DAG via :func:`_run_dag`.
       Otherwise falls back to the Sprint 19 single-task shortcut.
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
        tasks = list(
            session.scalars(
                select(JobTask).where(JobTask.job_id == job_id)
            ).all()
        )
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
            uc_client = UnityCatalogClient.for_principal(
                settings, user_info["email"]
            )
        except PointlessSQLError as exc:
            logger.warning(
                "scheduler: job %d principal client failed: %s", job_id, exc.detail
            )
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)

        if is_dag:
            try:
                ok, err = await _run_dag(
                    factory, registry, tasks, run_id, user_info, uc_client
                )
            except ValidationError as exc:
                logger.warning(
                    "scheduler: job %d DAG invalid: %s", job_id, exc.detail
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
                factory, run_id, None, "INFO",
                f"single-task job kind={kind} starting",
            )
            await executor(run_id, user_info, config, uc_client)
        except PointlessSQLError as exc:
            logger.warning(
                "scheduler: job %d (%s) failed: %s", job_id, kind, exc.detail
            )
            log_job(factory, run_id, None, "ERROR", exc.detail)
            with factory() as session:
                _finish_run(session, run_id, "failed", exc.detail)
            return _detached_run(factory, run_id)
        except Exception as exc:  # noqa: BLE001 — scheduler must not crash
            logger.exception(
                "scheduler: job %d (%s) raised unexpectedly", job_id, kind
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


def _detached_run(
    factory: sessionmaker[Session], run_id: int
) -> JobRun:
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
            await client.post(
                url, json=payload, timeout=_WEBHOOK_TIMEOUT_SECONDS
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "scheduler: on_failure_url webhook to %s failed: %s", url, exc
        )
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
        self._global_sem = asyncio.Semaphore(
            max(1, self._settings.scheduler_max_concurrent_runs)
        )
        self._per_job_sems = {}
        self._task = asyncio.create_task(self._run(), name="pointlessql-scheduler")
        logger.info(
            "scheduler: started (tick=%ds, max_concurrent=%d)",
            self._settings.scheduler_tick_seconds,
            self._settings.scheduler_max_concurrent_runs,
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
        tick_seconds = float(self._settings.scheduler_tick_seconds)
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


__all__ = [
    "JobExecutor",
    "KindRegistry",
    "Scheduler",
    "build_default_registry",
    "execute_run",
    "log_job",
    "tick_once",
    "validate_dag",
]
