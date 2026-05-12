"""Tests for ``POST /api/notebooks/save`` (Sprint 66.2)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app

_DEMO_NOTEBOOK = b"""\
# %%
print('hello')

# %% [markdown]
# Heading

# %% [sql] df
SELECT 1 AS n
"""


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin notebooks dir to an isolated tmp path."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_save_happy_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Save writes new content and returns refreshed content_hashes."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    payload = {
        "path": "demo.py",
        "cells": [
            {"cell_type": "code", "source": "x = 42"},
            {"cell_type": "markdown", "source": "# new heading"},
        ],
    }
    resp = await admin_client.post("/api/notebooks/save", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == "demo.py"
    assert isinstance(body["mtime"], (int, float))
    assert len(body["cells"]) == 2
    assert body["cells"][0]["cell_type"] == "code"
    assert body["cells"][1]["cell_type"] == "markdown"
    written = (workspace_dir / "demo.py").read_text()
    assert "x = 42" in written
    assert "# %% [markdown]" in written


async def test_save_mtime_conflict(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Stale ``expected_mtime`` → 409 with the conflict envelope."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    payload = {
        "path": "demo.py",
        "expected_mtime": 1.0,  # ancient — guaranteed stale
        "cells": [{"cell_type": "code", "source": "y = 1"}],
    }
    resp = await admin_client.post("/api/notebooks/save", json=payload)
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "mtime_conflict"
    assert isinstance(body["current_mtime"], (int, float))
    # File is unchanged
    assert b"print('hello')" in (workspace_dir / "demo.py").read_bytes()


async def test_save_roundtrip_stability(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Load → no-op-save reproduces the same logical structure on disk.

    Strict byte-equality is too strong (jupytext normalises trailing
    newlines + drops legacy markers); we assert the parsed cell
    sequence is identical instead.
    """
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    load_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    cells_in = load_resp.json()["cells"]

    save_payload = {
        "path": "demo.py",
        "cells": [
            {
                "cell_type": c["cell_type"],
                "source": c["source"],
                "result_var": c.get("result_var"),
            }
            for c in cells_in
        ],
    }
    save_resp = await admin_client.post("/api/notebooks/save", json=save_payload)
    assert save_resp.status_code == 200

    reload_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    cells_out = reload_resp.json()["cells"]
    # Cell types + sources + result_var preserved verbatim
    assert [c["cell_type"] for c in cells_out] == [c["cell_type"] for c in cells_in]
    assert [c["source"].rstrip() for c in cells_out] == [
        c["source"].rstrip() for c in cells_in
    ]
    assert [c.get("result_var") for c in cells_out] == [
        c.get("result_var") for c in cells_in
    ]


async def test_save_bad_cell_type(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown cell_type → 422 with the validation envelope."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.post(
        "/api/notebooks/save",
        json={
            "path": "demo.py",
            "cells": [{"cell_type": "raw", "source": "nope"}],
        },
    )
    assert resp.status_code == 422


async def test_save_traversal_blocked(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``../`` escape attempts must 422."""
    resp = await admin_client.post(
        "/api/notebooks/save",
        json={"path": "../escape.py", "cells": []},
    )
    assert resp.status_code == 422


async def test_save_non_admin_accessible(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Phase 70: any authenticated user can save a notebook."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await non_admin_client.post(
        "/api/notebooks/save",
        json={
            "path": "demo.py",
            "cells": [
                {
                    "cell_id": "0000000000000001",
                    "cell_type": "code",
                    "source": "print('member edit')\n",
                }
            ],
        },
    )
    assert resp.status_code == 200
