"""Phase 105.5 — save-path barrier tests.

Covers the ``apply_save_remap`` server-originated broadcast that
fires when ``/api/notebooks/save`` reconciles a client-tracked
``cell_uuid`` to a different canonical UUID.

All tests run through Starlette's :class:`TestClient` so the WS
hub + save handler share the same asyncio loop.  We avoid blocking
``receive_bytes()`` calls on the negative path (no broadcast
expected) — that path would deadlock because there is nothing to
receive — and only assert on the positive paths plus state
inspection on the hub's in-memory Doc.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from pycrdt import Array, Doc, Map, Text
from sqlalchemy import delete

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.main import app
from pointlessql.models import Notebook
from pointlessql.models.notebook import (
    NotebookCellIdentity,
    NotebookCrdtState,
    NotebookPermission,
)
from pointlessql.services.notebook.coedit import (
    CELLS_ORDER_KEY,
    CELLS_TEXT_KEY,
)

_TAG_SYNC_UPDATE = bytes([notebook_coedit_ws.TAG_SYNC_UPDATE])
_TAG_CELL_UUID_REMAP = bytes([notebook_coedit_ws.TAG_CELL_UUID_REMAP])


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin notebooks dir to an isolated tmp path."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


@pytest.fixture
def fresh_notebook_on_disk(workspace_dir: Path) -> Iterator[str]:
    """Seed a notebook .py + clean up the DB rows after the test."""
    rel = f"barrier-{uuid.uuid4().hex[:8]}.py"
    (workspace_dir / rel).write_bytes(b"# %%\nprint('seed')\n")
    yield rel
    factory = app.state.session_factory
    with factory() as session:
        nb_rows = list(
            session.execute(
                sqlalchemy.select(Notebook).where(Notebook.file_path == rel)
            ).scalars()
        )
        for nb in nb_rows:
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


def _build_seeded_client_doc(server_state_blob: bytes) -> Doc:
    doc = Doc()
    doc[CELLS_ORDER_KEY] = Array()
    doc[CELLS_TEXT_KEY] = Map()
    if server_state_blob:
        doc.apply_update(server_state_blob)
    return doc


def test_save_with_matching_cell_uuid_round_trips_unchanged(
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """Save preserving the client-tracked cell_uuid returns it unchanged.

    The reconciler's Pass-1 (exact content_hash match) returns the
    existing row id; the diff dict ends up empty so no broadcast
    fires.  We verify via the REST response — the absence of a
    broadcast is implicit (no hub state changes / no frame is sent)
    and impossible to assert directly without a deadlocking
    blocking receive on an empty queue.
    """
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        assert first.status_code == 200, first.text
        stable_uuid = first.json()["cells"][0]["cell_uuid"]
        assert stable_uuid
        second = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [
                    {
                        "cell_type": "code",
                        "source": "x = 1",
                        "cell_uuid": stable_uuid,
                    }
                ],
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["cells"][0]["cell_uuid"] == stable_uuid


def test_save_with_drifted_cell_uuid_broadcasts_remap(
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """Client-tracked uuid that drifts from the reconciler → remap fires.

    We send a save body with a fabricated ``cell_uuid`` that doesn't
    match the canonical row.  The reconciler's Pass-1 (exact hash)
    returns the real row id; the diff dict is non-empty and the WS
    subscriber sees ``0x04 + JSON``.
    """
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        assert first.status_code == 200, first.text
        notebook_uuid = first.json()["notebook_uuid"]
        real_cell_uuid = first.json()["cells"][0]["cell_uuid"]
        bogus_client_uuid = "bogus-" + uuid.uuid4().hex[:8]
        assert bogus_client_uuid != real_cell_uuid
        with client.websocket_connect(
            f"/ws/notebook/coedit/{notebook_uuid}"
        ) as ws:
            ws.receive_bytes()  # initial sync_step2
            client.post(
                "/api/notebooks/save",
                json={
                    "path": rel,
                    "cells": [
                        {
                            "cell_type": "code",
                            "source": "x = 1",
                            "cell_uuid": bogus_client_uuid,
                        }
                    ],
                },
            )
            # The broadcast fires synchronously inside the save
            # handler before it returns; receive_bytes() never
            # blocks indefinitely here.  Tolerate a small handful
            # of interleaved frames (sync_update echoes etc.).
            frame: bytes | None = None
            for _ in range(5):
                candidate = ws.receive_bytes()
                if candidate.startswith(_TAG_CELL_UUID_REMAP):
                    frame = candidate
                    break
    assert frame is not None
    payload = json.loads(frame[1:].decode("utf-8"))
    assert payload == {bogus_client_uuid: real_cell_uuid}


def test_save_with_drifted_uuid_rewrites_hub_doc(
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """After the remap, the hub's Doc holds the payload under the new key."""
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
        real_cell_uuid = first.json()["cells"][0]["cell_uuid"]
        bogus_client_uuid = "bogus-" + uuid.uuid4().hex[:8]
        with client.websocket_connect(
            f"/ws/notebook/coedit/{notebook_uuid}"
        ) as ws:
            initial = ws.receive_bytes()
            doc = _build_seeded_client_doc(initial[1:])
            doc[CELLS_TEXT_KEY][bogus_client_uuid] = Text("payload-text")
            doc[CELLS_ORDER_KEY].append(bogus_client_uuid)
            ws.send_bytes(_TAG_SYNC_UPDATE + doc.get_update())
            time.sleep(0.15)  # give the hub time to apply
            client.post(
                "/api/notebooks/save",
                json={
                    "path": rel,
                    "cells": [
                        {
                            "cell_type": "code",
                            "source": "x = 1",
                            "cell_uuid": bogus_client_uuid,
                        }
                    ],
                },
            )
            time.sleep(0.15)  # let the broadcast settle
            hub = notebook_coedit_ws._HUBS[notebook_uuid]
            order = list(hub.doc[CELLS_ORDER_KEY].to_py())
            texts = dict(hub.doc[CELLS_TEXT_KEY].to_py())
    assert bogus_client_uuid not in texts
    assert real_cell_uuid in texts
    assert str(texts[real_cell_uuid]) == "payload-text"
    assert bogus_client_uuid not in order
    assert real_cell_uuid in order


def test_save_without_active_hub_does_not_crash(
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """Drift-worthy save with no open hub → 200, no crash."""
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [{"cell_type": "code", "source": "x = 1"}],
            },
        )
        assert first.status_code == 200, first.text
        notebook_uuid = first.json()["notebook_uuid"]
        assert notebook_uuid not in notebook_coedit_ws._HUBS
        bogus = "bogus-" + uuid.uuid4().hex[:8]
        second = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [
                    {
                        "cell_type": "code",
                        "source": "x = 1",
                        "cell_uuid": bogus,
                    }
                ],
            },
        )
    assert second.status_code == 200, second.text


def test_save_with_partial_drift_remap_excludes_unchanged_uuids(
    auth_cookies: dict[str, str],
    fresh_notebook_on_disk: str,
) -> None:
    """Mixed drift: only the changed entry appears in the remap dict."""
    rel = fresh_notebook_on_disk
    with TestClient(app, cookies=auth_cookies) as client:
        first = client.post(
            "/api/notebooks/save",
            json={
                "path": rel,
                "cells": [
                    {"cell_type": "code", "source": "x = 1"},
                    {"cell_type": "code", "source": "y = 2"},
                ],
            },
        )
        notebook_uuid = first.json()["notebook_uuid"]
        cell_a_uuid = first.json()["cells"][0]["cell_uuid"]
        cell_b_uuid = first.json()["cells"][1]["cell_uuid"]
        bogus_b = "bogus-" + uuid.uuid4().hex[:8]
        with client.websocket_connect(
            f"/ws/notebook/coedit/{notebook_uuid}"
        ) as ws:
            ws.receive_bytes()  # initial sync_step2
            client.post(
                "/api/notebooks/save",
                json={
                    "path": rel,
                    "cells": [
                        {
                            "cell_type": "code",
                            "source": "x = 1",
                            "cell_uuid": cell_a_uuid,  # unchanged
                        },
                        {
                            "cell_type": "code",
                            "source": "y = 2",
                            "cell_uuid": bogus_b,  # drift
                        },
                    ],
                },
            )
            frame: bytes | None = None
            for _ in range(5):
                candidate = ws.receive_bytes()
                if candidate.startswith(_TAG_CELL_UUID_REMAP):
                    frame = candidate
                    break
    assert frame is not None
    payload = json.loads(frame[1:].decode("utf-8"))
    assert payload == {bogus_b: cell_b_uuid}
    assert cell_a_uuid not in payload
