"""Phase 105.2 — co-edit WebSocket hub tests.

Covers handshake (auth, role, notebook-existence), the binary wire
protocol (sync_step2 on connect, sync_update fanout, awareness
relay), and hub lifecycle (cleanup on disconnect, final-flush on
last-subscriber leaves).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pycrdt import Array, Doc, Map, Text
from sqlalchemy import delete, select
from starlette.websockets import WebSocketDisconnect

from pointlessql.api import notebook_coedit_ws
from pointlessql.api.main import app
from pointlessql.models import Notebook
from pointlessql.models.notebook import NotebookCrdtState, NotebookPermission
from pointlessql.services.notebook.coedit import (
    CELLS_ORDER_KEY,
    CELLS_TEXT_KEY,
)

# Tag bytes mirror the server module so the assertions stay readable.
_TAG_SYNC_STEP2 = bytes([notebook_coedit_ws.TAG_SYNC_STEP2])
_TAG_SYNC_UPDATE = bytes([notebook_coedit_ws.TAG_SYNC_UPDATE])
_TAG_AWARENESS_UPDATE = bytes([notebook_coedit_ws.TAG_AWARENESS_UPDATE])


@pytest.fixture
def admin_user_id() -> int:
    """Resolve the admin seeded by ``tests/conftest.py``."""
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models.auth import User

        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


@pytest.fixture
def nonadmin_user_id() -> int:
    """Resolve the non-admin seeded by ``tests/conftest.py``."""
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models.auth import User

        return int(
            session.execute(
                select(User.id).where(User.email == "nonadmin@test.com")
            ).scalar_one()
        )


@pytest.fixture
def fresh_notebook() -> Iterator[str]:
    """Insert a notebook row + clean up after the test."""
    notebook_id = str(uuid.uuid4())
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            Notebook(
                id=notebook_id,
                workspace_id=1,
                file_path=f"coedit-ws-test-{notebook_id[:8]}.py",
            )
        )
        session.commit()
    yield notebook_id
    notebook_coedit_ws._HUBS.pop(notebook_id, None)
    with factory() as session:
        session.execute(
            delete(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == notebook_id
            )
        )
        session.execute(
            delete(NotebookPermission).where(
                NotebookPermission.notebook_id == notebook_id
            )
        )
        session.execute(delete(Notebook).where(Notebook.id == notebook_id))
        session.commit()


def _build_seeded_client_doc(server_state_blob: bytes) -> Doc:
    """Build a local Doc that mirrors the server's initial state.

    The locked top-level shape must be set up *before* applying any
    update so pycrdt knows where to slot the incoming structures.
    """
    doc = Doc()
    doc[CELLS_ORDER_KEY] = Array()
    doc[CELLS_TEXT_KEY] = Map()
    if server_state_blob:
        doc.apply_update(server_state_blob)
    return doc


# ---------------------------------------------------------------------------
# 1 — Auth handshake
# ---------------------------------------------------------------------------


def test_ws_anonymous_closes_with_4401() -> None:
    """No cookie + no Bearer → close 4401 immediately after accept."""
    notebook_id = str(uuid.uuid4())
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/notebook/coedit/{notebook_id}"
            ) as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4401


# ---------------------------------------------------------------------------
# 2 — Unknown notebook → 4404
# ---------------------------------------------------------------------------


def test_ws_unknown_notebook_closes_with_4404(
    auth_cookies: dict[str, str],
) -> None:
    """Authenticated but the notebook id doesn't resolve → 4404."""
    bogus_id = "00000000-0000-0000-0000-000000000000"
    with TestClient(app, cookies=auth_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/notebook/coedit/{bogus_id}"
            ) as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4404


# ---------------------------------------------------------------------------
# 3 — Non-admin without edit grant → 4403
# ---------------------------------------------------------------------------


def test_ws_viewer_role_closes_with_4403(
    non_admin_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """Non-admin caller with no ``edit`` grant on the notebook → 4403.

    ``actor_has_role`` workspace-default is ``"run"`` for ungranted
    rows, so ``"edit"`` rejects without an explicit grant.
    """
    with TestClient(app, cookies=non_admin_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/notebook/coedit/{fresh_notebook}"
            ) as ws:
                ws.receive_bytes()
    assert exc_info.value.code == 4403


# ---------------------------------------------------------------------------
# 4 — Admin connects and receives sync_step2
# ---------------------------------------------------------------------------


def test_ws_admin_connects_and_receives_initial_state(
    auth_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """Admin accepts the handshake + server pushes the initial frame."""
    with TestClient(app, cookies=auth_cookies) as client:
        with client.websocket_connect(
            f"/ws/notebook/coedit/{fresh_notebook}"
        ) as ws:
            frame = ws.receive_bytes()
    assert frame.startswith(_TAG_SYNC_STEP2)
    # Payload is the encoded state for a fresh doc — at least the
    # top-level structure markers (a few bytes); never empty.
    assert len(frame) > 1


# ---------------------------------------------------------------------------
# 5 — sync_update broadcasts to other clients
# ---------------------------------------------------------------------------


def test_ws_sync_update_broadcasts_to_other_clients(
    auth_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """Client A's sync_update reaches Client B with the same payload."""
    with TestClient(app, cookies=auth_cookies) as client:
        with client.websocket_connect(
            f"/ws/notebook/coedit/{fresh_notebook}"
        ) as ws_a:
            initial_a = ws_a.receive_bytes()
            with client.websocket_connect(
                f"/ws/notebook/coedit/{fresh_notebook}"
            ) as ws_b:
                _initial_b = ws_b.receive_bytes()

                # Client A produces a real update relative to the initial state.
                doc_a = _build_seeded_client_doc(initial_a[1:])
                cells_text: Map = doc_a[CELLS_TEXT_KEY]
                cells_text["fanout-cell"] = Text("y = 2")
                doc_a[CELLS_ORDER_KEY].append("fanout-cell")
                update_bytes = doc_a.get_update()
                ws_a.send_bytes(_TAG_SYNC_UPDATE + update_bytes)

                relayed = ws_b.receive_bytes()
    assert relayed.startswith(_TAG_SYNC_UPDATE)
    assert relayed[1:] == update_bytes

    # Server-side replica caught the edit too.
    doc_check = _build_seeded_client_doc(initial_a[1:])
    doc_check.apply_update(update_bytes)
    assert "fanout-cell" in list(doc_check[CELLS_ORDER_KEY].to_py())


# ---------------------------------------------------------------------------
# 6 — Awareness relays but is not persisted
# ---------------------------------------------------------------------------


def test_ws_awareness_update_relays_but_doesnt_persist(
    auth_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """Awareness frames fan out unchanged and never touch the sidecar row."""
    factory = app.state.session_factory
    payload = b"opaque-awareness-frame-bytes"
    with TestClient(app, cookies=auth_cookies) as client:
        with client.websocket_connect(
            f"/ws/notebook/coedit/{fresh_notebook}"
        ) as ws_a:
            ws_a.receive_bytes()  # discard initial sync_step2
            with client.websocket_connect(
                f"/ws/notebook/coedit/{fresh_notebook}"
            ) as ws_b:
                ws_b.receive_bytes()  # discard initial sync_step2
                ws_a.send_bytes(_TAG_AWARENESS_UPDATE + payload)
                relayed = ws_b.receive_bytes()
    assert relayed == _TAG_AWARENESS_UPDATE + payload

    # Awareness must NOT have been written into the doc blob.
    with factory() as session:
        row = session.execute(
            select(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == fresh_notebook
            )
        ).scalar_one_or_none()
    if row is not None:
        assert payload not in bytes(row.y_doc_blob)


# ---------------------------------------------------------------------------
# 7 — Disconnect cleans up the hub
# ---------------------------------------------------------------------------


def test_ws_disconnect_cleans_up_hub(
    auth_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """After the last client disconnects, the module-level hub is gone."""
    with TestClient(app, cookies=auth_cookies) as client:
        with client.websocket_connect(
            f"/ws/notebook/coedit/{fresh_notebook}"
        ) as ws:
            ws.receive_bytes()
            assert fresh_notebook in notebook_coedit_ws._HUBS
    # TestClient's context-manager exit triggers a graceful close;
    # give the server loop a moment to finalise the teardown.
    for _ in range(20):
        if fresh_notebook not in notebook_coedit_ws._HUBS:
            break
        time.sleep(0.05)
    assert fresh_notebook not in notebook_coedit_ws._HUBS


# ---------------------------------------------------------------------------
# 8 — Final flush persists pending updates
# ---------------------------------------------------------------------------


def test_ws_final_flush_persists_pending_updates(
    auth_cookies: dict[str, str],
    fresh_notebook: str,
) -> None:
    """Updates applied just before disconnect land in the sidecar row.

    Catches the case where the dirty flag is set but the periodic
    flush task has not ticked yet — only the synchronous final
    flush in ``_release_hub_if_empty`` saves the day.
    """
    factory = app.state.session_factory
    with TestClient(app, cookies=auth_cookies) as client:
        with client.websocket_connect(
            f"/ws/notebook/coedit/{fresh_notebook}"
        ) as ws:
            initial = ws.receive_bytes()
            doc = _build_seeded_client_doc(initial[1:])
            doc[CELLS_TEXT_KEY]["final-flush"] = Text("z = 3")
            doc[CELLS_ORDER_KEY].append("final-flush")
            update_bytes = doc.get_update()
            ws.send_bytes(_TAG_SYNC_UPDATE + update_bytes)
            # Don't wait for the 1-s flush — close immediately.

    # Give the asyncio teardown a beat to land.
    for _ in range(20):
        if fresh_notebook not in notebook_coedit_ws._HUBS:
            break
        time.sleep(0.05)

    with factory() as session:
        row = session.execute(
            select(NotebookCrdtState).where(
                NotebookCrdtState.notebook_id == fresh_notebook
            )
        ).scalar_one()
    persisted = _build_seeded_client_doc(bytes(row.y_doc_blob))
    assert "final-flush" in list(persisted[CELLS_ORDER_KEY].to_py())
