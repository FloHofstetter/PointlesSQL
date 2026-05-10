"""API tests for the Phase-66.0 notebook CRUD routes.

Covers:

* ``POST   /api/notebooks/create``
* ``POST   /api/notebooks/rename``
* ``DELETE /api/notebooks/delete``

Read-only ``GET /api/notebooks/tree`` + ``/notebooks/workspace`` page
tests live in ``test_api_notebook_workspace.py``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


# -- POST /api/notebooks/create --


async def test_create_happy_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Create writes an empty ``.py`` file and returns the relative path."""
    resp = await admin_client.post(
        "/api/notebooks/create",
        json={"path": "demo.py"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"path": "demo.py"}
    assert (workspace_dir / "demo.py").is_file()


async def test_create_already_exists(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Pre-existing file → 422 with the validation envelope."""
    (workspace_dir / "exists.py").write_bytes(b"")
    resp = await admin_client.post(
        "/api/notebooks/create",
        json={"path": "exists.py"},
    )
    assert resp.status_code == 422


async def test_create_traversal_blocked(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``../`` escape attempts must 422 before touching the filesystem."""
    resp = await admin_client.post(
        "/api/notebooks/create",
        json={"path": "../escape.py"},
    )
    assert resp.status_code == 422
    assert not (workspace_dir.parent / "escape.py").exists()


async def test_create_non_admin_forbidden(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admins get a 403 envelope."""
    resp = await non_admin_client.post(
        "/api/notebooks/create",
        json={"path": "denied.py"},
    )
    assert resp.status_code == 403


# -- POST /api/notebooks/rename --


async def test_rename_happy_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Rename moves the file and returns the from/to pair."""
    (workspace_dir / "old.py").write_bytes(b"# %%\n1+1\n")
    resp = await admin_client.post(
        "/api/notebooks/rename",
        json={"from_path": "old.py", "to_path": "new.py"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"from_path": "old.py", "to_path": "new.py"}
    assert not (workspace_dir / "old.py").exists()
    assert (workspace_dir / "new.py").is_file()


async def test_rename_target_exists(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Existing target → 422; original file must remain untouched."""
    (workspace_dir / "src.py").write_bytes(b"")
    (workspace_dir / "dst.py").write_bytes(b"")
    resp = await admin_client.post(
        "/api/notebooks/rename",
        json={"from_path": "src.py", "to_path": "dst.py"},
    )
    assert resp.status_code == 422
    assert (workspace_dir / "src.py").exists()


# -- DELETE /api/notebooks/delete --


async def test_delete_requires_confirm(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Without ``confirm=true`` the delete must 400 and leave the file."""
    (workspace_dir / "kept.py").write_bytes(b"")
    resp = await admin_client.delete("/api/notebooks/delete?path=kept.py")
    assert resp.status_code == 400
    assert (workspace_dir / "kept.py").exists()


async def test_delete_happy_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Confirmed delete removes the file and returns its path."""
    (workspace_dir / "doomed.py").write_bytes(b"")
    resp = await admin_client.delete(
        "/api/notebooks/delete?path=doomed.py&confirm=true"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"path": "doomed.py"}
    assert not (workspace_dir / "doomed.py").exists()


async def test_delete_unknown_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown target → 422 (resolves but not a file)."""
    resp = await admin_client.delete(
        "/api/notebooks/delete?path=ghost.py&confirm=true"
    )
    assert resp.status_code == 422
