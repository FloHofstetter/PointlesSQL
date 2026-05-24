"""Smoke tests for the kernel WebSocket route.

Auth-rejection paths can be exercised without spawning a kernel
subprocess; full execute round-trips are exercised by the
browser-side integration test that drives ``execute → iopub-stream
→ execute_reply`` end-to-end.

The synchronous :class:`fastapi.testclient.TestClient` is used here
because httpx's async client does not natively speak WebSockets, and
the conftest's :data:`POINTLESSQL_TEST_LIFESPAN_FAST=1` short-circuit
keeps lifespan startup cheap so re-using the synchronous client per
test stays fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pointlessql.api.main import app
from pointlessql.services.notebook.kernel_session import KernelRegistry


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated tmp dir."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    monkeypatch.setattr(
        app.state,
        "kernel_registry",
        KernelRegistry(notebooks_dir=root),
        raising=False,
    )
    return root


def test_unauthenticated_ws_closes_with_4401(workspace_dir: Path) -> None:
    """No cookie + no Bearer → close code 4401 before kernel start."""
    (workspace_dir / "demo.py").write_bytes(b"# %%\nprint('hi')\n")
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/notebook/kernel?path=demo.py") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4401


# dropped the admin-only WS gate; ``_user_can_use_editor``
# now accepts any authenticated user, so the 4403 close code is no
# longer reachable from the cookie path. The test that exercised it
# was removed alongside the gate change.


def test_unknown_notebook_path_closes_with_4404(
    workspace_dir: Path, auth_cookies: dict[str, str]
) -> None:
    """Authenticated admin + missing file → close code 4404."""
    with TestClient(app, cookies=auth_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/notebook/kernel?path=ghost.py") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4404


def test_traversal_path_closes_with_4404(workspace_dir: Path, auth_cookies: dict[str, str]) -> None:
    """Path-traversal attempts close with 4404 before kernel start."""
    with TestClient(app, cookies=auth_cookies) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/notebook/kernel?path=../escape.py") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4404
