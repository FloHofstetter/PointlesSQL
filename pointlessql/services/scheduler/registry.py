# pyright: reportPrivateUsage=false
"""Executor registry + ``JobExecutor`` type alias.

Owns the :class:`KindRegistry` map of ``kind`` identifier → executor
coroutine plus the :func:`build_default_registry` factory that wires
the four built-in executors (``pg_sync``, ``python``, ``papermill``,
``alert_check``) on a fresh registry.

Built-in executor implementations live in :mod:`.executors` so this
module stays thin and circular-import-free.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

# Executor callable signature.  ``uc_client`` is a
# ``UnityCatalogClient`` built with ``for_principal(user.email)`` so
# soyuz's ``X-Principal`` applies. ``config`` is the deserialized
# ``jobs.config`` (single-task shortcut) or ``job_tasks.config`` (DAG
# task) dict. The executor returns ``None`` on success and raises on
# failure — the scheduler catches the exception, records it on the
# :class:`~pointlessql.models.JobRun` /
# :class:`~pointlessql.models.TaskRun`, and keeps ticking.
JobExecutor = Callable[
    [int, UserInfo, dict[str, Any], UnityCatalogClient],
    Awaitable[None],
]


class KindRegistry:
    """Mapping of ``kind`` identifier → executor coroutine.

    The registry is a plain object instead of a module-level ``dict``
    so tests can instantiate a fresh one per case without mutating
    shared state. The default registry populated by
    :func:`build_default_registry` seeds ``"pg_sync"``, ``"python"``,
    ``"papermill"``, and ``"alert_check"`` from
    :mod:`.executors`.
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


def build_default_registry() -> KindRegistry:
    """Return a :class:`KindRegistry` with the built-in executors wired up.

    Returns:
        A fresh registry with ``"pg_sync"``, ``"python"``, ``"papermill"``,
        ``"alert_check"``, ``"branch_cleanup"``, and ``"ingest_pull"``
        bound.
    """
    # Local import: executors module imports from registry, but registry
    # only needs the executors at factory-call time.
    from pointlessql.services.ingest.executor import ingest_pull_executor
    from pointlessql.services.scheduler.executors import (
        _alert_check_executor,
        _branch_cleanup_executor,
        _papermill_executor,
        _pg_sync_executor,
        _python_executor,
    )

    registry = KindRegistry()
    registry.register("pg_sync", _pg_sync_executor)
    registry.register("python", _python_executor)
    registry.register("papermill", _papermill_executor)
    registry.register("alert_check", _alert_check_executor)
    registry.register("branch_cleanup", _branch_cleanup_executor)
    registry.register("ingest_pull", ingest_pull_executor)
    return registry
