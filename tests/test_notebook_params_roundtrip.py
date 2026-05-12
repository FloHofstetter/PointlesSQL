"""Roundtrip tests for params-tag persistence (Phase 67.7).

The editor toggles ``parameters`` tags on individual cells via
``toggleParamsTag()`` and POSTs them through ``/api/notebooks/save``.
A subsequent ``GET /api/notebooks/load`` must surface the same tag
list so the inspector + jobs panel stay in sync with on-disk truth.
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


async def test_mark_params_save_reload(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    (workspace_dir / "demo.py").write_text("# %%\nx = 1\n")
    payload = {
        "path": "demo.py",
        "cells": [
            {
                "cell_type": "code",
                "source": "cutoff_date = '2026-05-10'",
                "tags": ["parameters"],
            },
            {
                "cell_type": "code",
                "source": "print(cutoff_date)",
                "tags": [],
            },
        ],
    }
    resp = await admin_client.post("/api/notebooks/save", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cells"][0]["tags"] == ["parameters"]
    assert body["cells"][1]["tags"] == []

    # On disk the marker carries the tags suffix in jupytext form.
    text = (workspace_dir / "demo.py").read_text()
    assert 'tags=["parameters"]' in text

    # Reload — tags round-trip.
    load = await admin_client.get("/api/notebooks/load", params={"path": "demo.py"})
    assert load.status_code == 200, load.text
    cells = load.json()["cells"]
    assert cells[0]["tags"] == ["parameters"]
    assert cells[1]["tags"] == []


async def test_unmark_params(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    (workspace_dir / "u.py").write_text(
        '# %% tags=["parameters"]\nx = 1\n'
    )
    payload = {
        "path": "u.py",
        "cells": [
            {"cell_type": "code", "source": "x = 1", "tags": []},
        ],
    }
    resp = await admin_client.post("/api/notebooks/save", json=payload)
    assert resp.status_code == 200, resp.text
    text = (workspace_dir / "u.py").read_text()
    assert "tags=" not in text


async def test_inspect_finds_marked_params(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """End-to-end: marking a cell makes /api/notebooks/inspect see params."""
    (workspace_dir / "e2e.py").write_text("# %%\nfoo = 7\n")
    payload = {
        "path": "e2e.py",
        "cells": [
            {
                "cell_type": "code",
                "source": "foo = 7",
                "tags": ["parameters"],
            },
        ],
    }
    save_resp = await admin_client.post("/api/notebooks/save", json=payload)
    assert save_resp.status_code == 200, save_resp.text
    inspect_resp = await admin_client.get(
        "/api/notebooks/inspect", params={"path": "e2e.py"}
    )
    assert inspect_resp.status_code == 200, inspect_resp.text
    names = {p["name"] for p in inspect_resp.json()}
    assert "foo" in names
