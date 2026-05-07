"""API tests for the notebooks workspace endpoints.

Covers:

* ``GET /api/notebooks/tree`` — admin-only; returns a nested listing
  with ``parameters_tagged`` flags; skips ``runs/``.
* ``GET /notebooks/workspace`` — admin-only HTML page; non-admins 403.

The upload endpoint that used to live at ``POST /api/notebooks/upload``
was removed in the agent-first pivot — humans no longer author
notebooks in the UI; agents drop ``.py`` jupytext files into
``notebooks/`` and the scheduler executes them.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app

_PARAM_IPYNB = json.dumps(
    {
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
).encode()




@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


# -- GET /api/notebooks/tree --


async def test_tree_returns_nested_listing(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """Happy path: nested folders + top-level notebooks surface in the JSON."""
    (workspace_dir / "pipelines").mkdir()
    (workspace_dir / "pipelines" / "etl.ipynb").write_bytes(_PARAM_IPYNB)
    (workspace_dir / "top.ipynb").write_bytes(_PARAM_IPYNB)

    resp = await admin_client.get("/api/notebooks/tree")

    assert resp.status_code == 200
    data = resp.json()
    dirs = [n for n in data if n["kind"] == "dir"]
    notebooks = [n for n in data if n["kind"] == "notebook"]
    assert [d["name"] for d in dirs] == ["pipelines"]
    assert [n["name"] for n in notebooks] == ["top.ipynb"]
    assert dirs[0]["children"][0]["parameters_tagged"] is True


async def test_tree_excludes_runs_dir(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """The executor's ``runs/`` output folder must not leak into the tree."""
    (workspace_dir / "runs").mkdir()
    (workspace_dir / "runs" / "99.ipynb").write_bytes(_PARAM_IPYNB)
    (workspace_dir / "real.ipynb").write_bytes(_PARAM_IPYNB)

    resp = await admin_client.get("/api/notebooks/tree")

    names = [n["name"] for n in resp.json()]
    assert "runs" not in names
    assert "real.ipynb" in names


async def test_tree_non_admin_forbidden(workspace_dir: Path, non_admin_client: httpx.AsyncClient) -> None:
    """The tree API is admin-only; non-admins get a 403 envelope."""
    resp = await non_admin_client.get("/api/notebooks/tree")
    assert resp.status_code == 403


# -- GET /notebooks/workspace HTML page --


async def test_workspace_page_admin_renders(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """Admins get the workspace HTML page with the upload card markup."""
    resp = await admin_client.get("/notebooks/workspace")
    assert resp.status_code == 200
    assert "Notebook workspace" in resp.text
    assert "notebookWorkspace()" in resp.text


async def test_workspace_page_non_admin_forbidden(workspace_dir: Path, non_admin_client: httpx.AsyncClient) -> None:
    """Non-admins bounce off the workspace page."""
    resp = await non_admin_client.get("/notebooks/workspace")
    assert resp.status_code == 403
