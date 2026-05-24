"""Unit tests for :mod:`pointlessql.services.notebook._workspace`.

The service adds a workspace file-browser surface on top of the
executor. These tests exercise the two pure helpers the service
exposes (``list_workspace_tree`` and ``resolve_upload_target``)
without touching the HTTP layer — the API-level contract is
covered by ``tests/test_api_notebook_workspace.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import (
    list_workspace_tree,
    resolve_upload_target,
)

_PARAM_IPYNB = {
    "cells": [
        {
            "cell_type": "code",
            "source": ["x = 1\n"],
            "outputs": [],
            "execution_count": None,
            "metadata": {"tags": ["parameters"]},
        }
    ],
    "metadata": {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

_NO_PARAM_IPYNB = {
    "cells": [
        {
            "cell_type": "code",
            "source": ["print('hi')\n"],
            "outputs": [],
            "execution_count": None,
            "metadata": {},
        }
    ],
    "metadata": {
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def _write(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


# -- list_workspace_tree --


def test_tree_empty_when_dir_missing(tmp_path: Path) -> None:
    """A notebooks dir that does not exist yields an empty list, not an error."""
    assert list_workspace_tree(tmp_path / "missing") == []


def test_tree_lists_top_level_notebooks(tmp_path: Path) -> None:
    """Flat layout: notebooks at the root are returned sorted by name."""
    _write(tmp_path / "zeta.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "alpha.ipynb", _NO_PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)
    assert [n["name"] for n in tree] == ["alpha.ipynb", "zeta.ipynb"]
    assert all(n["kind"] == "notebook" for n in tree)


def test_tree_nests_directories(tmp_path: Path) -> None:
    """Directories come before notebooks and carry ``children``."""
    _write(tmp_path / "pipelines" / "etl.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "top.ipynb", _NO_PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)

    assert tree[0]["kind"] == "dir"
    assert tree[0]["name"] == "pipelines"
    assert tree[0]["path"] == "pipelines"
    assert [c["name"] for c in tree[0]["children"]] == ["etl.ipynb"]
    assert tree[0]["children"][0]["path"] == "pipelines/etl.ipynb"

    assert tree[1]["kind"] == "notebook"
    assert tree[1]["name"] == "top.ipynb"


def test_tree_excludes_runs_directory(tmp_path: Path) -> None:
    """The top-level ``runs/`` subdir (executor output) is skipped entirely."""
    _write(tmp_path / "runs" / "1234.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "work.ipynb", _NO_PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)
    names = [n["name"] for n in tree]
    assert "runs" not in names
    assert names == ["work.ipynb"]


def test_tree_parameters_tagged_true_and_false(tmp_path: Path) -> None:
    """``parameters_tagged`` reflects whether a ``parameters``-tagged cell exists."""
    _write(tmp_path / "tagged.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "untagged.ipynb", _NO_PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)
    by_name = {n["name"]: n for n in tree}
    assert by_name["tagged.ipynb"]["parameters_tagged"] is True
    assert by_name["untagged.ipynb"]["parameters_tagged"] is False


def test_tree_handles_broken_notebook_gracefully(tmp_path: Path) -> None:
    """A malformed notebook surfaces as ``parameters_tagged=False`` rather than 500."""
    (tmp_path / "broken.ipynb").write_text("{not valid json")
    _write(tmp_path / "ok.ipynb", _PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)
    by_name = {n["name"]: n for n in tree}
    assert by_name["broken.ipynb"]["parameters_tagged"] is False
    assert by_name["ok.ipynb"]["parameters_tagged"] is True


def test_tree_ignores_non_ipynb_files(tmp_path: Path) -> None:
    """Non-``.ipynb`` files are not leaves in the tree."""
    (tmp_path / "README.md").write_text("# hi")
    _write(tmp_path / "real.ipynb", _PARAM_IPYNB)
    tree = list_workspace_tree(tmp_path)
    assert [n["name"] for n in tree] == ["real.ipynb"]


def test_tree_excludes_dot_prefixed_dirs_at_any_depth(tmp_path: Path) -> None:
    """BUG-27-01: ``.ipynb_checkpoints`` (and any dot-dir) is filtered.

    Jupyter writes ``.ipynb_checkpoints/<name>-checkpoint.ipynb`` next to
    every edited notebook. These are storage artefacts, not user content,
    so they must not appear in the workspace browser — top-level *and*
    nested (e.g. under ``pipelines/.ipynb_checkpoints/``).
    """
    _write(tmp_path / ".ipynb_checkpoints" / "foo-checkpoint.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "pipelines" / ".ipynb_checkpoints" / "etl-checkpoint.ipynb", _PARAM_IPYNB)
    _write(tmp_path / "pipelines" / "etl.ipynb", _PARAM_IPYNB)
    _write(tmp_path / ".hidden.ipynb", _PARAM_IPYNB)

    tree = list_workspace_tree(tmp_path)

    top_names = [n["name"] for n in tree]
    assert ".ipynb_checkpoints" not in top_names
    assert ".hidden.ipynb" not in top_names

    pipelines = next(n for n in tree if n["name"] == "pipelines")
    assert [c["name"] for c in pipelines["children"]] == ["etl.ipynb"]


# -- resolve_upload_target --


def test_upload_target_happy_path(tmp_path: Path) -> None:
    """A relative, non-existing ``.ipynb`` under the root resolves cleanly."""
    target = resolve_upload_target(tmp_path, "new.ipynb")
    assert target == tmp_path / "new.ipynb"
    assert not target.exists()  # upload has not happened yet


def test_upload_target_allows_existing_file(tmp_path: Path) -> None:
    """Pre-existence is the caller's problem; ``resolve_upload_target`` doesn't care."""
    (tmp_path / "existing.ipynb").write_text("{}")
    target = resolve_upload_target(tmp_path, "existing.ipynb")
    assert target == tmp_path / "existing.ipynb"


def test_upload_target_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        resolve_upload_target(tmp_path, "")


def test_upload_target_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must be relative"):
        resolve_upload_target(tmp_path, "/etc/passwd.ipynb")


def test_upload_target_rejects_non_ipynb_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match=r"\.ipynb"):
        resolve_upload_target(tmp_path, "script.py")


def test_upload_target_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "notebooks"
    root.mkdir()
    with pytest.raises(ValidationError, match="escapes"):
        resolve_upload_target(root, "../outside.ipynb")


def test_upload_target_rejects_missing_parent(tmp_path: Path) -> None:
    """The parent dir must exist so uploads don't create arbitrary nested folders."""
    with pytest.raises(ValidationError, match="parent directory"):
        resolve_upload_target(tmp_path, "nope/nested/file.ipynb")
