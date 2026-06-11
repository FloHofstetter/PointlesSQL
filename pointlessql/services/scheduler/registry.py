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

    def kinds(self) -> tuple[str, ...]:
        """Return the registered kind identifiers in registration order.

        The visual task-chain editor reads this to paint its block
        palette and to flag a node whose ``block_type`` is not a
        runnable kind, so the palette never drifts from what the
        scheduler can actually execute.
        """
        return tuple(self._executors)


def build_default_registry() -> KindRegistry:
    """Return a :class:`KindRegistry` with the built-in executors wired up.

    Returns:
        A fresh registry with ``"pg_sync"``, ``"python"``, ``"papermill"``,
        ``"alert_check"``, ``"branch_cleanup"``, ``"coedit_compaction"``,
        ``"policy_compliance"``, ``"ingest_pull"`` and
        ``"event_port_pump"`` bound.
    """
    # Local import: executors module imports from registry, but registry
    # only needs the executors at factory-call time.
    from pointlessql.services.bi_snapshots import bi_snapshot_executor
    from pointlessql.services.ingest.executor import ingest_pull_executor
    from pointlessql.services.pii_classification import pii_classification_executor
    from pointlessql.services.pipelines import pipeline_run_executor
    from pointlessql.services.quality_monitoring import quality_monitor_executor
    from pointlessql.services.scheduler.executors import (
        _alert_check_executor,
        _branch_cleanup_executor,
        _coedit_compaction_executor,
        _contract_test_evaluation_executor,
        _cost_rollup_hourly_executor,
        _entity_link_discovery_executor,
        _event_port_pump_executor,
        _papermill_executor,
        _pg_sync_executor,
        _policy_compliance_executor,
        _python_executor,
        _slo_evaluation_executor,
    )
    from pointlessql.services.synced_tables import sync_executor as table_sync_executor

    registry = KindRegistry()
    registry.register("pg_sync", _pg_sync_executor)
    registry.register("python", _python_executor)
    registry.register("papermill", _papermill_executor)
    registry.register("alert_check", _alert_check_executor)
    registry.register("branch_cleanup", _branch_cleanup_executor)
    registry.register("coedit_compaction", _coedit_compaction_executor)
    registry.register("policy_compliance", _policy_compliance_executor)
    registry.register("slo_evaluation", _slo_evaluation_executor)
    registry.register("ingest_pull", ingest_pull_executor)
    registry.register("pipeline_run", pipeline_run_executor)
    registry.register("table_sync", table_sync_executor)
    registry.register("event_port_pump", _event_port_pump_executor)
    registry.register("cost_rollup_hourly", _cost_rollup_hourly_executor)
    registry.register("contract_test_evaluation", _contract_test_evaluation_executor)
    registry.register("entity_link_discovery", _entity_link_discovery_executor)
    registry.register("pii_classification", pii_classification_executor)
    registry.register("bi_snapshot", bi_snapshot_executor)
    registry.register("quality_monitor", quality_monitor_executor)
    return registry
