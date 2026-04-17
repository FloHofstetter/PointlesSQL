"""API tests for the Sprint 27 workspace endpoints.

Covers:

* ``GET /api/notebooks/tree`` — admin-only; returns a nested listing
  with ``parameters_tagged`` flags; skips ``runs/``.
* ``POST /api/notebooks/upload`` — admin-only; rejects bad filenames,
  non-JSON bodies, traversal, and existing-file overwrites without
  the ``overwrite`` flag; writes atomically on the happy path.
* ``GET /notebooks/workspace`` — admin-only HTML page; non-admins 403.
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


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _non_admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    )


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.notebooks_dir`` at an isolated tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings, "notebooks_dir", root)
    return root


# -- GET /api/notebooks/tree --


async def test_tree_returns_nested_listing(workspace_dir: Path) -> None:
    """Happy path: nested folders + top-level notebooks surface in the JSON."""
    (workspace_dir / "pipelines").mkdir()
    (workspace_dir / "pipelines" / "etl.ipynb").write_bytes(_PARAM_IPYNB)
    (workspace_dir / "top.ipynb").write_bytes(_PARAM_IPYNB)

    async with _admin_client() as client:
        resp = await client.get("/api/notebooks/tree")

    assert resp.status_code == 200
    data = resp.json()
    dirs = [n for n in data if n["kind"] == "dir"]
    notebooks = [n for n in data if n["kind"] == "notebook"]
    assert [d["name"] for d in dirs] == ["pipelines"]
    assert [n["name"] for n in notebooks] == ["top.ipynb"]
    assert dirs[0]["children"][0]["parameters_tagged"] is True


async def test_tree_excludes_runs_dir(workspace_dir: Path) -> None:
    """The executor's ``runs/`` output folder must not leak into the tree."""
    (workspace_dir / "runs").mkdir()
    (workspace_dir / "runs" / "99.ipynb").write_bytes(_PARAM_IPYNB)
    (workspace_dir / "real.ipynb").write_bytes(_PARAM_IPYNB)

    async with _admin_client() as client:
        resp = await client.get("/api/notebooks/tree")

    names = [n["name"] for n in resp.json()]
    assert "runs" not in names
    assert "real.ipynb" in names


async def test_tree_non_admin_forbidden(workspace_dir: Path) -> None:
    """The tree API is admin-only; non-admins get a 403 envelope."""
    async with _non_admin_client() as client:
        resp = await client.get("/api/notebooks/tree")
    assert resp.status_code == 403


# -- POST /api/notebooks/upload --


async def test_upload_happy_path(workspace_dir: Path) -> None:
    """Admin uploads a valid .ipynb to a fresh path; file lands on disk."""
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("fresh.ipynb", _PARAM_IPYNB, "application/json")},
            data={"target_path": "fresh.ipynb"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"path": "fresh.ipynb", "status": "created"}
    assert (workspace_dir / "fresh.ipynb").read_bytes() == _PARAM_IPYNB
    assert not (workspace_dir / "fresh.ipynb.tmp").exists()


async def test_upload_rejects_non_ipynb_extension(workspace_dir: Path) -> None:
    """The server enforces .ipynb on the uploaded filename."""
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("script.py", b"print('hi')", "text/x-python")},
            data={"target_path": "script.py"},
        )
    assert resp.status_code == 422
    assert ".ipynb" in resp.json()["error"]["message"]


async def test_upload_rejects_invalid_json(workspace_dir: Path) -> None:
    """Uploaded file must parse as JSON; otherwise nothing touches disk."""
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={
                "file": (
                    "corrupt.ipynb",
                    b"{not valid json",
                    "application/json",
                )
            },
            data={"target_path": "corrupt.ipynb"},
        )
    assert resp.status_code == 422
    assert not (workspace_dir / "corrupt.ipynb").exists()


async def test_upload_rejects_traversal(workspace_dir: Path) -> None:
    """``..``-prefixed target paths escape the notebooks root → 422."""
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("x.ipynb", _PARAM_IPYNB, "application/json")},
            data={"target_path": "../escape.ipynb"},
        )
    assert resp.status_code == 422
    assert "escape" in resp.json()["error"]["message"].lower()


async def test_upload_rejects_existing_without_overwrite(
    workspace_dir: Path,
) -> None:
    """Repeat upload to the same path errors with a helpful message."""
    (workspace_dir / "dup.ipynb").write_bytes(_PARAM_IPYNB)
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("dup.ipynb", _PARAM_IPYNB, "application/json")},
            data={"target_path": "dup.ipynb"},
        )
    assert resp.status_code == 422
    assert "overwrite=true" in resp.json()["error"]["message"]


async def test_upload_overwrite_replaces_existing(workspace_dir: Path) -> None:
    """Passing ``overwrite=true`` replaces the existing file atomically."""
    (workspace_dir / "dup.ipynb").write_bytes(b"{}")
    async with _admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("dup.ipynb", _PARAM_IPYNB, "application/json")},
            data={"target_path": "dup.ipynb", "overwrite": "true"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "overwritten"
    assert (workspace_dir / "dup.ipynb").read_bytes() == _PARAM_IPYNB


async def test_upload_non_admin_forbidden(workspace_dir: Path) -> None:
    """Non-admins cannot upload notebooks."""
    async with _non_admin_client() as client:
        resp = await client.post(
            "/api/notebooks/upload",
            files={"file": ("nope.ipynb", _PARAM_IPYNB, "application/json")},
            data={"target_path": "nope.ipynb"},
        )
    assert resp.status_code == 403


# -- GET /notebooks/workspace HTML page --


async def test_workspace_page_admin_renders(workspace_dir: Path) -> None:
    """Admins get the workspace HTML page with the upload card markup."""
    async with _admin_client() as client:
        resp = await client.get("/notebooks/workspace")
    assert resp.status_code == 200
    assert "Notebook workspace" in resp.text
    assert "notebookWorkspace()" in resp.text


async def test_workspace_page_non_admin_forbidden(workspace_dir: Path) -> None:
    """Non-admins bounce off the workspace page."""
    async with _non_admin_client() as client:
        resp = await client.get("/notebooks/workspace")
    assert resp.status_code == 403
