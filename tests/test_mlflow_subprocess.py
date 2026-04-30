"""Tests for the MLflow subprocess lifecycle manager (Phase 21.0).

These tests cover URI derivation + the import-availability check
without actually spawning ``mlflow server`` (slow, port-bound,
flaky). End-to-end "subprocess actually starts and answers /health"
coverage lives in the manual lifespan smoke test in the closure
section of the Phase 21 plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pointlessql.services.mlflow_subprocess import (
    MLflowSubprocess,
    mlflow_available,
)
from pointlessql.settings import MLflowSettings


def test_mlflow_available_with_optional_extra_installed() -> None:
    """[ml] extra is in dev-deps so the import-spec lookup succeeds."""
    assert mlflow_available() is True


def test_derive_uris_uses_defaults_from_cwd(tmp_path: Path) -> None:
    """Default URIs anchor to the passed cwd, not Path.cwd() at module load."""
    settings = MLflowSettings()
    proc = MLflowSubprocess(
        settings=settings,
        soyuz_url="http://127.0.0.1:8080",
        cwd=tmp_path,
    )
    backend, artifact_root, registry = proc._derive_uris()

    assert backend == "sqlite:///./mlflow.db"
    assert artifact_root == f"file://{tmp_path.resolve()}/mlflow_artifacts"
    # MLflow's UC-OSS scheme is `uc:` followed by the bare HTTP URL —
    # NOT `uc-oss:` (see Phase 21.1's uc_oss_proto_diff.md).
    assert registry == "uc:http://127.0.0.1:8080"


def test_derive_uris_respects_explicit_overrides(tmp_path: Path) -> None:
    """Explicit settings override every derived default."""
    settings = MLflowSettings(
        backend_store_uri="postgresql://user@db/mlflow",
        artifact_root="s3://bucket/mlflow",
        registry_uri="uc:http://prod-uc:9090",
    )
    proc = MLflowSubprocess(
        settings=settings,
        soyuz_url="http://localhost:8080",
        cwd=tmp_path,
    )
    backend, artifact_root, registry = proc._derive_uris()
    assert backend == "postgresql://user@db/mlflow"
    assert artifact_root == "s3://bucket/mlflow"
    assert registry == "uc:http://prod-uc:9090"


def test_pid_file_path_is_under_cwd(tmp_path: Path) -> None:
    """PID file lives in the cwd so multi-instance deployments don't collide."""
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
        cwd=tmp_path,
    )
    assert proc.pid_file == tmp_path / "mlflow.pid"


@pytest.mark.asyncio
async def test_stop_is_idempotent_when_proc_is_none(tmp_path: Path) -> None:
    """stop() before start() is a no-op, not an error."""
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
        cwd=tmp_path,
    )
    # No assertion needed — just must not raise.
    await proc.stop()


@pytest.mark.asyncio
async def test_health_returns_false_when_proc_is_none(tmp_path: Path) -> None:
    """health() before start() reports False without hitting the network."""
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
        cwd=tmp_path,
    )
    assert await proc.health() is False
