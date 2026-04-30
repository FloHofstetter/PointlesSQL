"""Training-block wrapper that forces MLflow autolog (Phase 21.3).

``pql.training_context()`` is the entry point an agent uses to wrap
a training call (sklearn ``.fit()``, torch loop, …).  Inside the
``with``:

* ``mlflow.autolog()`` is enabled with the framework hint the caller
  supplied (``"auto"`` by default — covers sklearn, xgboost, torch,
  tensorflow, pytorch-lightning out of the box).
* An ``mlflow.start_run()`` opens a tracking run when one is not
  already active.  When one IS already active (typical inside an
  outer Hermes orchestration) we reuse it via ``nested=True`` so
  PointlesSQL never silently steals an outer run.
* The wrapped block runs.
* On exit, ``MlflowClient.get_run(run_id)`` is called to read the
  final ``params`` + ``metrics`` dicts; we serialise them and stash
  them on the :class:`OperationRecorder` so
  :func:`record_operation` writes them onto
  ``agent_run_operations.training_params_json``.

The whole layer is **best-effort**: if the ``mlflow`` extra is
not installed, or if any sub-step raises, the wrapper degrades to
a plain :func:`operation_context` with no autolog and an empty
``training_params_json``.  Training failures are NEVER blocked by
audit-side problems — that's the inverse of the Phase-13.8 forced-
audit rule for write paths, but matches the ROADMAP "auditability
of intent, not bit-replay" framing.

Usage::

    from pointlessql.pql.pql import PQL

    pql = PQL(agent_run_id="run-123")
    with pql.training_context() as tr:
        model.fit(X, y)
        # mlflow.autolog has captured params+metrics by now
    # tr.mlflow_run_id is set if MLflow was reachable
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pointlessql.services.agent_runs.mlflow_detector import get_mlflow_module
from pointlessql.services.agent_runs.operations import (
    OperationRecorder,
    operation_context,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

_logger = logging.getLogger(__name__)


@dataclass
class TrainingRecorder:
    """Lightweight handle returned by :func:`training_context`.

    Attributes:
        mlflow_run_id: The active MLflow run-id when autolog was
            engaged, or ``None`` when MLflow was unavailable.
        framework: Framework hint passed in (``"auto"`` by default).
        op: The underlying :class:`OperationRecorder` so callers
            can stash extra params on it if needed.
        captured: Cached ``{"params", "metrics"}`` snapshot copied
            out of MLflow at run-exit time, or ``{}`` when capture
            was skipped.
    """

    mlflow_run_id: str | None = None
    framework: str = "auto"
    op: OperationRecorder | None = None
    captured: dict[str, Any] = field(default_factory=dict)


def _enable_autolog(mlflow: Any, framework: str) -> bool:
    """Best-effort wrapper around ``mlflow.autolog`` / framework-specific calls.

    Args:
        mlflow: The MLflow module returned by :func:`get_mlflow_module`.
        framework: ``"auto"`` or one of ``"sklearn"`` / ``"pytorch"`` /
            ``"tensorflow"`` / ``"xgboost"`` / ``"lightgbm"``.

    Returns:
        ``True`` when autolog was enabled, ``False`` when it raised
        (the wrapper degrades to a passthrough).
    """
    try:
        if framework == "auto":
            mlflow.autolog(disable_for_unsupported_versions=True)
            return True
        flavor = getattr(mlflow, framework, None)
        if flavor is None or not hasattr(flavor, "autolog"):
            mlflow.autolog(disable_for_unsupported_versions=True)
            return True
        flavor.autolog(disable_for_unsupported_versions=True)
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort capture
        _logger.warning(
            "training_context: autolog enable failed (framework=%s): %s",
            framework,
            exc,
        )
        return False


def _capture_run_data(mlflow: Any, run_id: str) -> dict[str, Any]:
    """Read ``params`` + ``metrics`` from an MLflow run, never raises.

    Args:
        mlflow: The MLflow module.
        run_id: Active MLflow run-id captured at start.

    Returns:
        ``{"params": {...}, "metrics": {...}}`` or an empty dict
        on lookup failure.
    """
    try:
        client = mlflow.MlflowClient()
        run = client.get_run(run_id)
        return {
            "params": dict(run.data.params),
            "metrics": dict(run.data.metrics),
        }
    except Exception as exc:  # noqa: BLE001 — best-effort capture
        _logger.warning("training_context: get_run(%s) failed: %s", run_id, exc)
        return {}


@contextmanager
def training_context(
    session_factory: sessionmaker[Session] | None,
    *,
    agent_run_id: str | None,
    framework: str = "auto",
    op_name: str = "train_model",
    params: dict[str, Any] | None = None,
) -> Iterator[TrainingRecorder]:
    """Wrap a training block: enable autolog, capture params/metrics at exit.

    Best-effort: if MLflow is not installed, the wrapper still
    yields a :class:`TrainingRecorder` and runs the block under
    :func:`operation_context` — the audit row lands without
    training-params content.

    Args:
        session_factory: SQLAlchemy session factory (required when
            ``agent_run_id`` is set; passed through to
            :func:`operation_context`).
        agent_run_id: Owning PointlesSQL agent-run UUID.  When
            ``None``, the wrapper is a passthrough — useful for
            interactive development.
        framework: ``"auto"`` (default) or any sub-flavor MLflow
            ships an ``autolog()`` for (``"sklearn"``,
            ``"pytorch"`` …).
        op_name: Audit-row label.  Default ``"train_model"`` is
            already in :data:`VALID_OP_NAMES`.
        params: Optional initial params dict.  Defaults to
            ``{"framework": framework}``.

    Yields:
        :class:`TrainingRecorder` exposing ``mlflow_run_id`` once
        the run is active.

    Raises:
        Exception: Re-raises whatever the wrapped block raised
            after the audit row + best-effort autolog snapshot have
            been captured.
    """  # noqa: DOC502 — re-raises wrapped exceptions
    initial_params: dict[str, Any] = params or {"framework": framework}
    rec = TrainingRecorder(framework=framework)
    mlflow = get_mlflow_module()
    autolog_active = False
    if mlflow is not None:
        autolog_active = _enable_autolog(mlflow, framework)

    with operation_context(
        session_factory,
        agent_run_id=agent_run_id,
        op_name=op_name,
        params=initial_params,
    ) as op_recorder:
        rec.op = op_recorder

        if mlflow is None or not autolog_active:
            # Best-effort passthrough — yield then exit normally.
            yield rec
            return

        active = None
        try:
            active = mlflow.active_run()
        except Exception:  # noqa: BLE001 — defensive
            active = None

        run_ctx = mlflow.start_run(nested=active is not None)
        try:
            with run_ctx as mlflow_run:
                rec.mlflow_run_id = mlflow_run.info.run_id
                op_recorder.extra_params = {
                    **op_recorder.extra_params,
                    "mlflow_run_id": rec.mlflow_run_id,
                    "framework": framework,
                }
                yield rec
                # Capture AFTER the body — autolog has fired by now.
                if rec.mlflow_run_id:
                    rec.captured = _capture_run_data(mlflow, rec.mlflow_run_id)
        except Exception:
            # If the body raised, still try to capture what autolog
            # had recorded before the failure (often partial params).
            if rec.mlflow_run_id:
                rec.captured = _capture_run_data(mlflow, rec.mlflow_run_id)
            raise
        finally:
            if rec.captured:
                op_recorder.training_params_json = json.dumps(
                    rec.captured, sort_keys=True, default=str
                )
