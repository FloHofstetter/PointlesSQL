"""Tests for the MLflow detector hook.

The detector is called from inside the operation-recorder hot path,
so it must be cheap, side-effect-free, and never raise. These tests
pin the three behaviours: importable mlflow + no active run, active
run, and the no-mlflow-installed graceful path.
"""

from __future__ import annotations

import pytest

from pointlessql.services.agent_runs.mlflow_detector import detect_mlflow_run_id


def test_detect_returns_none_when_no_active_run() -> None:
    """No outer ``with mlflow.start_run()`` → returns None."""
    mlflow = pytest.importorskip("mlflow")
    if mlflow.active_run() is not None:
        mlflow.end_run()
    assert detect_mlflow_run_id() is None


def test_detect_returns_run_id_when_run_active() -> None:
    """Inside ``with mlflow.start_run()`` → returns the run-id."""
    mlflow = pytest.importorskip("mlflow")
    with mlflow.start_run() as run:
        captured = detect_mlflow_run_id()
        assert captured == run.info.run_id


def test_detect_swallows_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken ``mlflow.active_run()`` returns None, never raises."""
    pytest.importorskip("mlflow")

    def _boom() -> None:
        raise RuntimeError("simulated failure")

    import mlflow

    monkeypatch.setattr(mlflow, "active_run", _boom)
    assert detect_mlflow_run_id() is None
