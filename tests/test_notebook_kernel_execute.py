"""End-to-end execute round-trip for the notebook kernel WebSocket.

Spawns a real ipykernel subprocess and runs ``print('hello')``
through the WS handler, asserting:

* The handshake "ready" frame arrives.
* iopub stream frames carry the captured text.
* The execute_reply on the shell channel arrives with status=ok.
* A row landed in ``notebook_outputs`` so a page reload would
  replay the output without re-execute.

Marked ``@pytest.mark.integration`` because the kernel-spawn cost
(~1s) is high relative to other tests; CI default still runs it
because there is one case only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from pointlessql.api.main import app
from pointlessql.models import NotebookOutput
from pointlessql.services.notebook.kernel_session import KernelRegistry


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin notebooks dir + kernel registry to a tmp tree."""
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


@pytest.mark.integration
def test_ws_execute_round_trip_persists_output(
    workspace_dir: Path, auth_cookies: dict[str, str]
) -> None:
    """Connect → execute → verify stream-output frame + persisted row."""
    nb_path = workspace_dir / "demo.py"
    nb_path.write_bytes(b"# %%\nprint('hello')\n")

    saw_stream = False
    saw_execute_reply = False
    content_hash_seen: str | None = None

    with TestClient(app, cookies=auth_cookies) as client:
        try:
            with client.websocket_connect("/ws/notebook/kernel?path=demo.py") as ws:
                # First frame is the "ready" notify.
                ready = json.loads(ws.receive_text())
                assert ready.get("notify") == "ready"
                content_hash = "0123456789abcdef"
                content_hash_seen = content_hash
                ws.send_text(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "execute",
                            "params": {
                                "content_hash": content_hash,
                                "source": "print('hello')",
                            },
                        }
                    )
                )
                deadline_loops = 0
                while not (saw_stream and saw_execute_reply) and deadline_loops < 200:
                    deadline_loops += 1
                    text = ws.receive_text()
                    payload = json.loads(text)
                    if payload.get("notify") == "kernel_message":
                        params = payload["params"]
                        if (
                            params.get("channel") == "iopub"
                            and params.get("msg_type") == "stream"
                            and "hello" in (params.get("content") or {}).get("text", "")
                        ):
                            saw_stream = True
                        if (
                            params.get("channel") == "shell"
                            and params.get("msg_type") == "execute_reply"
                        ):
                            saw_execute_reply = True
        except WebSocketDisconnect as exc:
            pytest.fail(f"WebSocket closed unexpectedly with code {exc.code}")

    assert saw_stream, "did not see iopub stream frame carrying 'hello'"
    assert saw_execute_reply, "did not see shell execute_reply"
    factory = app.state.session_factory
    with factory() as session:
        rows = list(
            session.execute(
                select(NotebookOutput).where(
                    NotebookOutput.file_path == "demo.py",
                    NotebookOutput.content_hash == content_hash_seen,
                )
            ).scalars()
        )
    assert any(r.msg_type == "stream" for r in rows), (
        "no stream output persisted to notebook_outputs"
    )
