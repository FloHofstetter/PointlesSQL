"""Tests for ``GET /api/notebooks/inspect`` (Phase 67.1).

The endpoint reuses :func:`papermill.inspect_notebook` to extract the
parameter declarations from a notebook's ``parameters``-tagged cell.
Phase 67 needs this to work for ``.py`` jupytext notebooks (the
canonical on-disk format post Phase 12.10) so the Schedule + Run-Once
modals can build a typed form. The endpoint converts ``.py`` to a
transient ``.ipynb`` before calling papermill so the caller never
sees the difference.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


def _write(workspace_dir: Path, name: str, body: str) -> None:
    (workspace_dir / name).write_text(body)


async def test_no_params_cell_returns_empty(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """A notebook without a parameters-tagged cell returns ``[]``."""
    _write(workspace_dir, "plain.py", "# %%\nprint('hello')\n")
    resp = await admin_client.get("/api/notebooks/inspect", params={"path": "plain.py"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_single_param_extracted(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``# %% tags=["parameters"]`` + ``x = 1`` → one entry."""
    body = '# %% tags=["parameters"]\nx = 1\n\n# %%\nprint(x)\n'
    _write(workspace_dir, "single.py", body)
    resp = await admin_client.get("/api/notebooks/inspect", params={"path": "single.py"})
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "x"
    # Papermill returns the literal source-text default — we don't coerce here.
    assert entry["default"] == "1"
    assert entry["inferred_type"] in {"int", "str", "None"}


async def test_typed_param_with_default(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """A typed param survives the conversion + inspection."""
    body = (
        '# %% tags=["parameters"]\n'
        'cutoff_date: str = "2026-05-01"\n'
        "window_days: int = 7\n\n"
        "# %%\nprint(cutoff_date, window_days)\n"
    )
    _write(workspace_dir, "typed.py", body)
    resp = await admin_client.get("/api/notebooks/inspect", params={"path": "typed.py"})
    assert resp.status_code == 200, resp.text
    names = {entry["name"] for entry in resp.json()}
    assert names == {"cutoff_date", "window_days"}


async def test_traversal_blocked(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``../`` escape attempts must 422 before touching the filesystem."""
    resp = await admin_client.get(
        "/api/notebooks/inspect", params={"path": "../escape.py"}
    )
    assert resp.status_code == 422


async def test_non_admin_forbidden(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admins must not introspect notebooks."""
    _write(workspace_dir, "x.py", "# %%\nx = 1\n")
    resp = await non_admin_client.get(
        "/api/notebooks/inspect", params={"path": "x.py"}
    )
    assert resp.status_code == 403
