"""repo-backed notebook path resolution.

The scheduler's :func:`resolve_notebook_path` accepts a
``repo:<workspace_id>:<slug>/<rel>.py`` spec that resolves
against the workspace-repos clone tree instead of the legacy
``notebooks_dir``.  Repo-backed notebooks are read-only; edits
flow through the team's git tool / PR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.scheduler.executors import (
    _REPO_PREFIX,
    resolve_notebook_path,
)


def test_resolve_notebook_path_accepts_repo_prefix(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    base_dir = tmp_path / "repos"
    clone_dir = base_dir / "1" / "data-team"
    clone_dir.mkdir(parents=True)
    notebook = clone_dir / "etl" / "bronze.py"
    notebook.parent.mkdir(parents=True)
    notebook.write_text("# notebook stub\n")

    monkeypatch.setenv("POINTLESSQL_REPOS_BASE_DIR", str(base_dir))

    spec = f"{_REPO_PREFIX}1:data-team/etl/bronze.py"
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    resolved = resolve_notebook_path(notebooks_dir, spec)
    assert resolved == notebook.resolve()


def test_resolve_notebook_path_rejects_traversal(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    base_dir = tmp_path / "repos"
    clone_dir = base_dir / "1" / "data-team"
    clone_dir.mkdir(parents=True)
    monkeypatch.setenv("POINTLESSQL_REPOS_BASE_DIR", str(base_dir))

    spec = f"{_REPO_PREFIX}1:data-team/../escape.py"
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    with pytest.raises(ValidationError):
        resolve_notebook_path(notebooks_dir, spec)


def test_resolve_notebook_path_repo_missing_clone_dir(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("POINTLESSQL_REPOS_BASE_DIR", str(tmp_path / "repos"))
    spec = f"{_REPO_PREFIX}1:never-synced/foo.py"
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    with pytest.raises(ValidationError, match="clone directory does not exist"):
        resolve_notebook_path(notebooks_dir, spec)


def test_resolve_notebook_path_repo_invalid_spec(tmp_path):  # type: ignore[no-untyped-def]
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    bad_specs = [
        f"{_REPO_PREFIX}data-team/foo.py",  # no workspace_id
        f"{_REPO_PREFIX}1:data-team",  # no relative path
        f"{_REPO_PREFIX}abc:data-team/foo.py",  # non-numeric workspace_id
        f"{_REPO_PREFIX}1:data-team/foo.txt",  # bad suffix
    ]
    for spec in bad_specs:
        with pytest.raises(ValidationError):
            resolve_notebook_path(notebooks_dir, spec)


def test_resolve_notebook_path_legacy_path_unaffected(tmp_path):  # type: ignore[no-untyped-def]
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    notebook = notebooks_dir / "demo.py"
    notebook.write_text("# stub\n")
    resolved = resolve_notebook_path(notebooks_dir, "demo.py")
    assert resolved == notebook.resolve()


def test_resolve_notebook_path_repo_file_missing(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    base_dir = tmp_path / "repos"
    clone_dir = base_dir / "1" / "data-team"
    clone_dir.mkdir(parents=True)
    monkeypatch.setenv("POINTLESSQL_REPOS_BASE_DIR", str(base_dir))

    spec = f"{_REPO_PREFIX}1:data-team/missing.py"
    notebooks_dir = tmp_path / "notebooks"
    notebooks_dir.mkdir()
    with pytest.raises(ValidationError, match="notebook not found"):
        resolve_notebook_path(notebooks_dir, spec)


def test_repo_prefix_constant():  # type: ignore[no-untyped-def]
    # Documents the wire format so external schedulers can produce specs.
    assert _REPO_PREFIX == "repo:"
    assert isinstance(_REPO_PREFIX, str)


# The Path import keeps the test module's typing surface honest.
_ = Path
