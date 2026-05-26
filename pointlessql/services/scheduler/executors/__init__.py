# pyright: reportPrivateUsage=false
"""Built-in job executors split per kind.

Executors are split per kind so each new job-type lives in its own
file with the helpers it needs.  Every executor matches the
:data:`pointlessql.services.scheduler.registry.JobExecutor` signature
and gets wired into
:func:`pointlessql.services.scheduler.registry.build_default_registry`
through the function-level imports below.

All cross-module imports inside executor bodies stay function-local
(``pg_sync``, ``alerts``, ``pql.pql``, ``authorization``) to dodge a
circular import chain through ``pointlessql.db`` and ``models``.
"""

from __future__ import annotations

from pointlessql.services.scheduler.executors.alert_check import (
    _alert_check_executor,
)
from pointlessql.services.scheduler.executors.branch_cleanup import (
    _branch_cleanup_executor,
)
from pointlessql.services.scheduler.executors.coedit_compaction import (
    _coedit_compaction_executor,
)
from pointlessql.services.scheduler.executors.papermill import (
    _PAPERMILL_INPUT_SUFFIXES,
    _REPO_PREFIX,
    _jupytext_py_to_ipynb,
    _papermill_env_lock,
    _papermill_executor,
    _persist_papermill_outputs,
    _resolve_repo_notebook_path,
    _run_papermill_blocking,
    resolve_notebook_path,
)
from pointlessql.services.scheduler.executors.pg_sync import _pg_sync_executor
from pointlessql.services.scheduler.executors.python import _python_executor

__all__ = [
    "_PAPERMILL_INPUT_SUFFIXES",
    "_REPO_PREFIX",
    "_alert_check_executor",
    "_branch_cleanup_executor",
    "_coedit_compaction_executor",
    "_jupytext_py_to_ipynb",
    "_papermill_env_lock",
    "_papermill_executor",
    "_persist_papermill_outputs",
    "_pg_sync_executor",
    "_python_executor",
    "_resolve_repo_notebook_path",
    "_run_papermill_blocking",
    "resolve_notebook_path",
]
