# pyright: reportPrivateUsage=false
"""In-process cron-style scheduler with multi-task DAG execution.

Supports multi-task DAGs, per-task retries, structured logging, and
concurrency caps.  The package is split across the following sibling
modules:

* :mod:`.registry` — :class:`KindRegistry`, :data:`JobExecutor` type
  alias, :func:`build_default_registry`.
* :mod:`.executors` — built-in executors ``_pg_sync_executor``,
  ``_python_executor``, ``_papermill_executor`` (+ helpers
  ``resolve_notebook_path``, ``_run_papermill_blocking``,
  ``_jupytext_py_to_ipynb``), ``_alert_check_executor``.
* :mod:`.dag` — pure DAG primitives ``validate_dag``,
  ``_topological_order``, ``_parse_depends_on``.
* :mod:`.runs` — task + run lifecycle: DB helpers,
  :func:`log_job`, ``_run_one_task``, ``_run_dag``,
  :func:`execute_run`, ``_emit_run_telemetry``,
  ``_post_failure_webhook``.  Owns the test-hook globals
  ``_sleep`` / ``_webhook_client_factory`` /
  ``_WEBHOOK_TIMEOUT_SECONDS`` — tests monkeypatch them on
  :mod:`pointlessql.services.scheduler.runs` directly.
* :mod:`.loop` — :func:`tick_once`, ``_execute_with_semaphores``,
  the :class:`Scheduler` driver class.

The package re-exports every name the API layer, scheduler tests,
and external docs reference so existing
``from pointlessql.services.scheduler import X`` and
``from pointlessql.services import scheduler as scheduler_service``
keep working unchanged.
"""

from __future__ import annotations

from pointlessql.services.scheduler.dag import (
    _parse_depends_on,
    _topological_order,
    validate_dag,
)
from pointlessql.services.scheduler.executors import (
    _alert_check_executor,
    _papermill_executor,
    _pg_sync_executor,
    _python_executor,
    resolve_notebook_path,
)
from pointlessql.services.scheduler.loop import (
    Scheduler,
    _execute_with_semaphores,
    tick_once,
)
from pointlessql.services.scheduler.registry import (
    JobExecutor,
    KindRegistry,
    build_default_registry,
)
from pointlessql.services.scheduler.runs import (
    _WEBHOOK_TIMEOUT_SECONDS,
    _emit_run_telemetry,
    _execute_run_core,
    _is_due,
    _post_failure_webhook,
    _sleep,
    _webhook_client_factory,
    execute_run,
    log_job,
)
from pointlessql.services.scheduler.runs._logic import (
    NOTIFY_ON_CHOICES,
    RUN_IF_CHOICES,
    TRIGGER_KINDS,
)
from pointlessql.services.scheduler.triggers import evaluate_event_trigger

__all__ = [
    "JobExecutor",
    "KindRegistry",
    "NOTIFY_ON_CHOICES",
    "RUN_IF_CHOICES",
    "Scheduler",
    "TRIGGER_KINDS",
    "_WEBHOOK_TIMEOUT_SECONDS",
    "_alert_check_executor",
    "_emit_run_telemetry",
    "_execute_run_core",
    "_execute_with_semaphores",
    "_is_due",
    "_papermill_executor",
    "_parse_depends_on",
    "_pg_sync_executor",
    "_post_failure_webhook",
    "_python_executor",
    "_sleep",
    "_topological_order",
    "_webhook_client_factory",
    "build_default_registry",
    "evaluate_event_trigger",
    "execute_run",
    "log_job",
    "resolve_notebook_path",
    "tick_once",
    "validate_dag",
]
