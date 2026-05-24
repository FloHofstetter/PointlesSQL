"""agent-presence REST endpoint tests.

Covers the ``POST /api/notebooks/{notebook_id}/coedit/agent-presence``
endpoint that lets a backend agent advertise its in-flight cell
mutation as a pseudo-peer on the co-edit channel.  The endpoint
serialises a JSON payload onto a new ``0x05 TAG_AGENT_PRESENCE``
wire frame and broadcasts it through the Phase-105.2 hub's
``_broadcast_to_all`` helper.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import delete

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.main import app
from pointlessql.api.notebook_coedit_agent_routes import TAG_AGENT_PRESENCE
from pointlessql.models import Notebook
from pointlessql.models.notebook import (
    NotebookCellIdentity,
    NotebookCrdtState,
    NotebookPermission,
)


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


@pytest.fixture
def fresh_notebook_on_disk(workspace_dir: Path) -> Iterator[str]:
    rel = f"agent-presence-{uuid.uuid4().hex[:8]}.py"
    (workspace_dir / rel).write_bytes(b"# %%\nprint('seed')\n")
    yield rel
    factory = app.state.session_factory
    with factory() as session:
        nbs = list(
            session.execute(
                sqlalchemy.select(Notebook).where(Notebook.file_path == rel)
            ).scalars()
        )
        for nb in nbs:
            notebook_coedit_ws._HUBS.pop(nb.id, None)
            session.execute(
                delete(NotebookCrdtState).where(
                    NotebookCrdtState.notebook_id == nb.id
                )
            )
            session.execute(
                delete(NotebookPermission).where(
                    NotebookPermission.notebook_id == nb.id
                )
            )
            session.execute(
                delete(NotebookCellIdentity).where(
                    NotebookCellIdentity.notebook_id == nb.id
                )
            )
            session.delete(nb)
        session.commit()


async def test_agent_presence_requires_auth(
    fresh_notebook_on_disk: str,
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous callers cannot push agent presence."""
    # Anon hits the editor page → notebook gets created lazily, but
    # for the API path we need an existing id, so we just call with
    # a synthetic uuid; auth fires first, before the 404.
    bogus_uuid = "00000000-0000-0000-0000-000000000000"
    resp = await anonymous_client.post(
        f"/api/notebooks/{bogus_uuid}/coedit/agent-presence",
        json={
            "agent_run_id": "run-1",
            "name": "hermes",
            "cell_uuid": None,
            "action": "editing",
        },
    )
    assert resp.status_code in (401, 403)


async def test_agent_presence_unknown_notebook_404s(
    admin_client: httpx.AsyncClient,
) -> None:
    """Authenticated caller + unknown notebook → 404."""
    bogus_uuid = "00000000-0000-0000-0000-000000000000"
    resp = await admin_client.post(
        f"/api/notebooks/{bogus_uuid}/coedit/agent-presence",
        json={
            "agent_run_id": "run-1",
            "name": "hermes",
            "cell_uuid": None,
            "action": "editing",
        },
    )
    assert resp.status_code == 404


def test_agent_presence_no_hub_returns_no_hub_status(
    workspace_dir: Path,
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """Presence push without any open WS → 200 + ``status="no-hub"``."""
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        notebook_uuid = first.json()["notebook_uuid"]
        assert notebook_uuid not in notebook_coedit_ws._HUBS
        resp = client.post(
            f"/api/notebooks/{notebook_uuid}/coedit/agent-presence",
            json={
                "agent_run_id": "run-no-hub",
                "name": "hermes",
                "cell_uuid": None,
                "action": "editing",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "no-hub"


def test_agent_presence_broadcasts_to_connected_clients(
    workspace_dir: Path,
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """With an open WS, the REST push broadcasts a ``0x05`` frame."""
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        notebook_uuid = first.json()["notebook_uuid"]
        with client.websocket_connect(
            f"/ws/notebook/coedit/{notebook_uuid}"
        ) as ws:
            ws.receive_bytes()  # initial sync_step2
            resp = client.post(
                f"/api/notebooks/{notebook_uuid}/coedit/agent-presence",
                json={
                    "agent_run_id": "run-42",
                    "name": "hermes",
                    "cell_uuid": "cell-xyz",
                    "action": "editing",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "broadcast"
            frame: bytes | None = None
            for _ in range(5):
                candidate = ws.receive_bytes()
                if candidate and candidate[0] == TAG_AGENT_PRESENCE:
                    frame = candidate
                    break
    assert frame is not None
    payload = json.loads(frame[1:].decode("utf-8"))
    assert payload["agent_run_id"] == "run-42"
    assert payload["name"] == "hermes"
    assert payload["cell_uuid"] == "cell-xyz"
    assert payload["action"] == "editing"


def test_agent_presence_clear_action_relays_unchanged(
    workspace_dir: Path,
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """``action="clear"`` flows through the wire as-is (mixin removes peer)."""
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        notebook_uuid = first.json()["notebook_uuid"]
        with client.websocket_connect(
            f"/ws/notebook/coedit/{notebook_uuid}"
        ) as ws:
            ws.receive_bytes()
            client.post(
                f"/api/notebooks/{notebook_uuid}/coedit/agent-presence",
                json={
                    "agent_run_id": "run-clear",
                    "name": "hermes",
                    "cell_uuid": None,
                    "action": "clear",
                },
            )
            frame: bytes | None = None
            for _ in range(5):
                candidate = ws.receive_bytes()
                if candidate and candidate[0] == TAG_AGENT_PRESENCE:
                    frame = candidate
                    break
    assert frame is not None
    payload = json.loads(frame[1:].decode("utf-8"))
    assert payload["action"] == "clear"
