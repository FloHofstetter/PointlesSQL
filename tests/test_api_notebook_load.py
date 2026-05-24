"""Tests for the Phase-66.1 ``GET /api/notebooks/load`` route + editor page."""

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


# -- GET /api/notebooks/load --


async def test_load_happy_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Load returns parsed cells with content_hash + cell_type set."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/api/notebooks/load?path=demo.py")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == "demo.py"
    assert isinstance(body["cells"], list)
    assert len(body["cells"]) == 3
    types = [c["cell_type"] for c in body["cells"]]
    assert types == ["code", "markdown", "sql"]
    sql_cell = body["cells"][2]
    assert sql_cell["result_var"] == "df"
    assert all(len(c["content_hash"]) == 16 for c in body["cells"])
    assert body["outputs"] == []


async def test_load_traversal_blocked(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``../`` escape attempts must 422."""
    resp = await admin_client.get("/api/notebooks/load?path=../escape.py")
    assert resp.status_code == 422


async def test_load_unknown_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Missing notebook → 422 with the validation envelope."""
    resp = await admin_client.get("/api/notebooks/load?path=ghost.py")
    assert resp.status_code == 422


async def test_load_non_admin_accessible(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """any authenticated user can load a notebook."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await non_admin_client.get("/api/notebooks/load?path=demo.py")
    assert resp.status_code == 200
    assert isinstance(resp.json().get("cells"), list)


# -- GET /notebooks/edit/{path:path} HTML page --


async def test_editor_page_renders(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Admin gets the editor HTML with the Alpine root + path injected."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    body = resp.text
    assert "notebookEditor(" in body
    assert "demo.py" in body


async def test_editor_page_unknown_path_blocks(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Editor page must 422 on a missing notebook before rendering."""
    resp = await admin_client.get("/notebooks/edit/ghost.py")
    assert resp.status_code == 422


async def test_editor_page_non_admin_accessible(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """any authenticated user reaches the editor page."""
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await non_admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    assert "notebookEditor(" in resp.text


async def test_editor_page_ships_coedit_scaffold(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """editor HTML carries the y-* importmap + live pill.

    Smoke-level check that the three scaffold pieces shipped with
    105.3 actually reach the rendered page:

    * ``yjs`` importmap entry (in the inherited ``base.html``).
    * ``y-protocols/awareness`` importmap entry (reserved for the
      Phase-105.4 cursor presence layer).
    * The toolbar co-edit status dot ``data-testid="notebook-coedit-dot"``
      (Sprint 112.5 — replaces the verbose ``notebook-coedit-pill``
      with one of three vital-sign dots in the toolbar).
    """
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    body = resp.text
    assert '"yjs":' in body
    assert '"y-protocols/awareness":' in body
    assert 'data-testid="notebook-coedit-dot"' in body


async def test_editor_page_ships_user_context(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """editor page injects the viewer's id + name.

    The Alpine root reads ``currentUser`` so the awareness layer can
    tag local cursors and paint the peer-rail with a stable colour /
    initials per viewer.  The id is the integer DB row id; the name
    falls back to ``email`` when ``display_name`` is empty.
    """
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    body = resp.text
    # The x-data attribute embeds ``currentUser`` as a JS object
    # literal — values come through ``tojson`` but the keys stay
    # unquoted JS identifiers.  ``id: 1`` / ``name: "..."`` is the
    # canonical shape; an integer > 0 + a non-empty quoted string
    # confirm the server-side threading reached the template.
    assert "currentUser" in body
    assert "id: 1" in body or "id:1" in body
    assert "name: " in body


async def test_editor_page_ships_coedit_peer_rail(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """editor HTML includes the peer-avatar rail partial.

    Smoke-level assertion on ``data-testid="notebook-coedit-peers"``
    so the playwright multi-tab gate has a stable
    selector to target.
    """
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    assert 'data-testid="notebook-coedit-peers"' in resp.text


async def test_editor_page_ships_y_codemirror_importmap(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """editor page exposes y-codemirror.next via importmap.

    The per-cell ``yCollab`` extension lives in ``y-codemirror.next``
    and is pulled in lazily by ``cellEditor()``.  An importmap entry
    therefore has to reach the editor HTML; otherwise the dynamic
    ``import('y-codemirror.next')`` would 404 against esm.sh.
    """
    (workspace_dir / "demo.py").write_bytes(_DEMO_NOTEBOOK)
    resp = await admin_client.get("/notebooks/edit/demo.py")
    assert resp.status_code == 200
    assert '"y-codemirror.next":' in resp.text
