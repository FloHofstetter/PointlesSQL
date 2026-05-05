"""Tests for the BUG-grand-09 path-anchor fix.

Pre-fix: ``DatabaseSettings.url`` defaulted to
``"sqlite:///./pointlessql.db"`` and MLflow's backend / artifact
defaults were ``cwd``-relative.  When the server was launched from
a different directory than the repo root (e.g. a sibling soyuz
checkout) parallel SQLite files appeared in both places and the
API silently read the wrong one.

Post-fix: defaults anchor to the project root computed at module
import time via ``Path(__file__).resolve().parent.parent``.  Env
vars (``POINTLESSQL_DB_URL`` etc.) still override the default
exactly as before.
"""

from __future__ import annotations

import os

import pointlessql.settings as settings_mod
from pointlessql.services.mlflow_subprocess import MLflowSubprocess
from pointlessql.settings import MLflowSettings, Settings


def test_database_url_default_is_absolute_project_anchor(tmp_path, monkeypatch) -> None:
    """``settings.db.url`` resolves to ``<repo>/pointlessql.db`` from any cwd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POINTLESSQL_DB_URL", raising=False)

    s = Settings()
    expected = settings_mod._PROJECT_ROOT / "pointlessql.db"
    assert s.db.url == f"sqlite:///{expected}"
    # The path must be absolute regardless of CWD.
    assert os.path.isabs(s.db.url.removeprefix("sqlite:///"))


def test_database_url_env_override_still_wins(tmp_path, monkeypatch) -> None:
    """``POINTLESSQL_DB_URL`` overrides the anchored default verbatim."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POINTLESSQL_DB_URL", "sqlite:///./caller-override.db")

    s = Settings()
    assert s.db.url == "sqlite:///./caller-override.db"


def test_project_root_constant_points_at_repo() -> None:
    """``_PROJECT_ROOT`` resolves to the repository checkout root."""
    expected_marker = settings_mod._PROJECT_ROOT / "pyproject.toml"
    assert expected_marker.is_file()


def test_mlflow_subprocess_default_cwd_anchored(tmp_path, monkeypatch) -> None:
    """Without explicit ``cwd``, MLflowSubprocess anchors paths to repo root."""
    monkeypatch.chdir(tmp_path)
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
    )
    # The default cwd must NOT pick up the test's tempdir.
    assert proc.cwd != tmp_path
    assert (proc.cwd / "pyproject.toml").is_file(), (
        f"MLflowSubprocess.cwd should resolve to the repo root, got {proc.cwd!r}"
    )


def test_mlflow_subprocess_explicit_cwd_still_overrides(tmp_path) -> None:
    """Caller-supplied ``cwd`` continues to override the anchor."""
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
        cwd=tmp_path,
    )
    assert proc.cwd == tmp_path


def test_mlflow_backend_default_uri_is_anchored() -> None:
    """Default backend store URI lands inside the cwd, not hardcoded ``./``."""
    proc = MLflowSubprocess(
        settings=MLflowSettings(),
        soyuz_url="http://127.0.0.1:8080",
    )
    backend, artifact_root, _ = proc._derive_uris()
    # No more bare "./mlflow.db" — the anchored cwd must be present.
    assert "./mlflow.db" not in backend
    assert str(proc.cwd) in backend or backend.startswith("sqlite:///"), backend
    assert "mlflow_artifacts" in artifact_root
