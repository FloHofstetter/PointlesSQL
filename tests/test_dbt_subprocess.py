"""Tests for the dbt-docs subprocess lifecycle manager.

Covers path resolution, project-readiness gating, and idempotent
shutdown.  Real spawn-and-poll coverage lives in the manual
lifespan smoke test outlined in the Phase 36 plan — spawning
``dbt docs serve`` here would be slow, port-bound, and would
require dbt-duckdb to be importable on the CI runner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pointlessql.config import DBTSettings
from pointlessql.services.dbt import (
    DBTStartupError,
    DBTSubprocess,
)


def test_path_resolution_against_cwd(tmp_path: Path) -> None:
    """Relative project + profiles dirs anchor to the passed cwd."""
    settings = DBTSettings()
    proj = tmp_path / "examples" / "dbt_project"
    proc = DBTSubprocess(settings=settings, cwd=tmp_path)
    assert proc.project_dir == proj.resolve()
    assert proc.profiles_dir == (proj / "profiles").resolve()
    assert proc.manifest_path == (proj / "target" / "manifest.json").resolve()


def test_path_resolution_keeps_absolute_paths(tmp_path: Path) -> None:
    """Absolute project + profiles paths pass through untouched."""
    abs_project = tmp_path / "elsewhere" / "proj"
    abs_profiles = tmp_path / "elsewhere" / "profs"
    settings = DBTSettings(project_dir=abs_project, profiles_dir=abs_profiles)
    proc = DBTSubprocess(settings=settings, cwd=tmp_path / "different")
    assert proc.project_dir == abs_project
    assert proc.profiles_dir == abs_profiles


def test_project_ready_false_without_manifest(tmp_path: Path) -> None:
    """A project dir without ``target/manifest.json`` is not ready."""
    project = tmp_path / "p"
    project.mkdir()
    proc = DBTSubprocess(settings=DBTSettings(project_dir=project), cwd=tmp_path)
    assert proc.project_ready() is False


def test_project_ready_false_without_project_dir(tmp_path: Path) -> None:
    """A non-existent project dir is not ready."""
    proc = DBTSubprocess(
        settings=DBTSettings(project_dir=tmp_path / "missing"),
        cwd=tmp_path,
    )
    assert proc.project_ready() is False


def test_project_ready_true_with_manifest(tmp_path: Path) -> None:
    """A project dir with a manifest.json is ready."""
    project = tmp_path / "p"
    target = project / "target"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(json.dumps({"nodes": {}}))
    proc = DBTSubprocess(settings=DBTSettings(project_dir=project), cwd=tmp_path)
    assert proc.project_ready() is True


def test_pid_file_path_is_under_cwd(tmp_path: Path) -> None:
    """PID file lives in the cwd so concurrent installs don't collide."""
    proc = DBTSubprocess(settings=DBTSettings(), cwd=tmp_path)
    assert proc.pid_file == tmp_path / "dbt_docs.pid"


@pytest.mark.asyncio
async def test_start_raises_when_project_not_ready(tmp_path: Path) -> None:
    """start() refuses to spawn dbt-docs when the manifest is missing."""
    proc = DBTSubprocess(
        settings=DBTSettings(project_dir=tmp_path / "missing"),
        cwd=tmp_path,
    )
    with pytest.raises(DBTStartupError, match="manifest"):
        await proc.start()


@pytest.mark.asyncio
async def test_stop_is_idempotent_when_proc_is_none(tmp_path: Path) -> None:
    """stop() before start() is a no-op, not an error."""
    proc = DBTSubprocess(settings=DBTSettings(), cwd=tmp_path)
    await proc.stop()  # should not raise
    assert proc.proc is None


@pytest.mark.asyncio
async def test_health_returns_false_when_proc_is_none(tmp_path: Path) -> None:
    """health() before start() is False, not an exception."""
    proc = DBTSubprocess(settings=DBTSettings(), cwd=tmp_path)
    assert await proc.health() is False
