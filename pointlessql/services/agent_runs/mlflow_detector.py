"""MLflow context detection for the operation-recorder hook.

The cross-link layer in :mod:`pointlessql.services.agent_runs.operations`
calls :func:`detect_mlflow_run_id` after every successful primitive
to check whether an MLflow Tracking run was active in the calling
process. If yes, the run-id gets stamped onto both the
``agent_run_operations`` row and (lazily, on first detection) the
parent ``agent_runs`` row so audits can join the three IDs without
out-of-band lookups.

The detector is import-tolerant — when the optional ``mlflow`` extra
isn't installed (``pip install pointlessql[ml]``), this module's
public function returns ``None`` immediately. That keeps the
recorder hot-path free of heavy imports for non-ML deployments.
"""

from __future__ import annotations

import functools
import importlib
import importlib.util
import logging
from typing import Any

_logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_mlflow_module() -> Any | None:
    """Import ``mlflow`` lazily, caching success/failure for the process.

    Returns:
        The imported ``mlflow`` module, or ``None`` if the optional
        extra is not installed.
    """
    if importlib.util.find_spec("mlflow") is None:
        return None
    try:
        return importlib.import_module("mlflow")
    except Exception:  # noqa: BLE001 - defensive against broken installs
        _logger.exception("mlflow import failed; cross-link disabled")
        return None


def detect_mlflow_run_id() -> str | None:
    """Return the active MLflow run-id, or ``None``.

    Called from the operation-recorder after every successful
    primitive. Side-effect-free; safe to invoke from non-ML ops.

    Returns:
        The active MLflow run-id, or ``None`` if MLflow isn't
        installed, no run is active, or the active-run query
        unexpectedly raises.
    """
    mlflow = get_mlflow_module()
    if mlflow is None:
        return None
    try:
        active = mlflow.active_run()
    except Exception:  # noqa: BLE001 — never let detection raise into the recorder
        # bare-broad-ok: detection must be silent (called per-op, hot path)
        return None
    if active is None:
        return None
    info = getattr(active, "info", None)
    if info is None:
        return None
    return getattr(info, "run_id", None)


# Backwards-compatible alias kept private for existing imports.
_mlflow_module = get_mlflow_module
