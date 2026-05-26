# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Job + task run lifecycle, structured logging, and failure-webhook telemetry.

The four concerns are split along the natural axes:

* :mod:`._db`        — DB helpers used by both the loop and the execution body.
* :mod:`._tasks`     — per-task lifecycle + DAG walker + the ``_sleep`` test hook.
* :mod:`._telemetry` — Prometheus metrics + failure webhook + its test hooks.
* :mod:`._execute`   — ``execute_run`` + ``_execute_run_core`` + ``_detached_run``.

The re-exports below match the pre-split import surface so call-sites in
``scheduler/__init__.py``, ``scheduler/loop.py``, and the test files
that import private helpers (``test_user_owned_workspace_isolation.py``)
need no edits.  Tests that monkeypatch the ``_sleep`` /
``_webhook_client_factory`` /  ``_WEBHOOK_TIMEOUT_SECONDS`` test hooks
do so via the original ``scheduler_service.runs.<name>`` path, which
this ``__init__`` keeps intact.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pointlessql.services.scheduler.runs._db import (
    _count_running_runs,
    _finish_run,
    _insert_skipped,
    _is_due,
    _last_run_started,
    _load_job_by_id,
    _load_user_info,
    _start_run,
    _utcnow,
    _workspace_id_for_job,
    _workspace_id_for_job_run,
    log_job,
)
from pointlessql.services.scheduler.runs._execute import (
    _detached_run,
    _execute_run_core,
    execute_run,
)
from pointlessql.services.scheduler.runs._tasks import (
    _create_task_run,
    _run_dag,
    _run_one_task,
    _update_task_run,
)
from pointlessql.services.scheduler.runs._telemetry import (
    _WEBHOOK_TIMEOUT_SECONDS,
    _duration_seconds,
    _emit_run_telemetry,
    _load_job_name_and_webhook,
    _post_failure_webhook,
    _webhook_client_factory,
    _WebhookClientFactory,
)

# Test hook for retry backoff — module-attribute so
# ``monkeypatch.setattr(runs, "_sleep", ...)`` reaches the call site
# in ``_tasks.py`` (which looks it up via ``runs._sleep`` at call time).
_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

__all__ = [
    "_WEBHOOK_TIMEOUT_SECONDS",
    "_WebhookClientFactory",
    "_count_running_runs",
    "_create_task_run",
    "_detached_run",
    "_duration_seconds",
    "_emit_run_telemetry",
    "_execute_run_core",
    "_finish_run",
    "_insert_skipped",
    "_is_due",
    "_last_run_started",
    "_load_job_by_id",
    "_load_job_name_and_webhook",
    "_load_user_info",
    "_post_failure_webhook",
    "_run_dag",
    "_run_one_task",
    "_sleep",
    "_start_run",
    "_update_task_run",
    "_utcnow",
    "_webhook_client_factory",
    "_workspace_id_for_job",
    "_workspace_id_for_job_run",
    "execute_run",
    "log_job",
]
