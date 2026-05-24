"""Server-side cell-management roundtrip tests .

Cell ops (add / delete / move / convert) are pure client-side state;
the server-visible contract is that POST /api/notebooks/save accepts
arbitrary cell layouts and load-after-save preserves them.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin notebooks dir."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def _save(
    client: httpx.AsyncClient,
    *,
    path: str,
    cells: list[dict[str, object]],
) -> dict[str, object]:
    resp = await client.post(
        "/api/notebooks/save",
        json={"path": path, "cells": cells},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_save_after_add_cell_below(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Inserting a new cell + saving keeps the new cell visible on reload."""
    (workspace_dir / "demo.py").write_bytes(b"# %%\nprint(1)\n")
    body = await _save(
        admin_client,
        path="demo.py",
        cells=[
            {"cell_type": "code", "source": "print(1)"},
            {"cell_type": "code", "source": "print(2)"},
        ],
    )
    assert len(body["cells"]) == 2
    reload_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    rcells = reload_resp.json()["cells"]
    assert [c["source"].strip() for c in rcells] == ["print(1)", "print(2)"]


async def test_save_after_move_cell_up(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Reordered cells round-trip correctly."""
    (workspace_dir / "demo.py").write_bytes(b"# %%\nprint('a')\n# %%\nprint('b')\n")
    await _save(
        admin_client,
        path="demo.py",
        cells=[
            {"cell_type": "code", "source": "print('b')"},
            {"cell_type": "code", "source": "print('a')"},
        ],
    )
    reload_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    rcells = reload_resp.json()["cells"]
    assert rcells[0]["source"].strip() == "print('b')"
    assert rcells[1]["source"].strip() == "print('a')"


async def test_save_after_delete_cell(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """Deleting cells via save (omitting them from the payload) shrinks the file."""
    (workspace_dir / "demo.py").write_bytes(b"# %%\n1\n# %%\n2\n# %%\n3\n")
    body = await _save(
        admin_client,
        path="demo.py",
        cells=[
            {"cell_type": "code", "source": "1"},
            {"cell_type": "code", "source": "3"},
        ],
    )
    assert len(body["cells"]) == 2
    reload_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    rcells = reload_resp.json()["cells"]
    assert [c["source"].strip() for c in rcells] == ["1", "3"]


async def test_save_cell_type_conversion(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Converting a code cell to markdown / sql round-trips the new type."""
    (workspace_dir / "demo.py").write_bytes(b"# %%\nprint(1)\n")
    await _save(
        admin_client,
        path="demo.py",
        cells=[
            {"cell_type": "markdown", "source": "# heading"},
            {
                "cell_type": "sql",
                "source": "SELECT 1",
                "result_var": "df",
            },
        ],
    )
    reload_resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    rcells = reload_resp.json()["cells"]
    assert [c["cell_type"] for c in rcells] == ["markdown", "sql"]
    assert rcells[1]["result_var"] == "df"
