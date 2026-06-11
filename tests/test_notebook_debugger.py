"""Tests for the notebook step-through debugger plumbing.

Three layers:

* The JSON-RPC ``debug`` handler proxies one DAP request to
  :meth:`KernelSession.debug_request` and returns the reply verbatim
  (or a structured error envelope) — exercised against a fake
  session, no kernel subprocess.
* ``debug_event`` iopub frames are forwarded by
  ``handle_kernel_message`` as a dedicated ``debug_event`` notify
  *before* the content-hash routing (they carry none) and are never
  persisted.
* ``@pytest.mark.integration``: a real ipykernel answers a
  ``debugInfo`` DAP request over the control channel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pointlessql.api.notebook_kernel_ws._handlers import handle_debug
from pointlessql.api.notebook_kernel_ws._pump import handle_kernel_message
from pointlessql.services.notebook.kernel_session import KernelMessage


class _FakeWebSocket:
    """Capture outbound frames as parsed JSON."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


class _FakeKernelSession:
    """Stand-in for :class:`KernelSession` recording debug requests."""

    session_id = "fake-session-id"

    def __init__(
        self,
        reply: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.requests: list[dict[str, Any]] = []
        self._reply = reply if reply is not None else {}
        self._error = error

    async def debug_request(self, content: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(content)
        if self._error is not None:
            raise self._error
        return self._reply


def _forbidden_factory() -> Any:
    """Session factory that fails the test when the pump touches it."""
    raise AssertionError("persistence factory must not be called for debug events")


async def test_handle_debug_proxies_request_and_reply() -> None:
    """``debug`` params.content goes to the session; reply comes back."""
    reply = {
        "type": "response",
        "success": True,
        "command": "debugInfo",
        "body": {"isStarted": False, "breakpoints": []},
    }
    session = _FakeKernelSession(reply=reply)
    websocket = _FakeWebSocket()
    content = {"command": "debugInfo", "arguments": {}}

    await handle_debug(
        websocket,  # type: ignore[arg-type]
        request_id=7,
        params={"content": content},
        session=session,  # type: ignore[arg-type]
    )

    assert session.requests == [content]
    assert websocket.sent == [{"id": 7, "result": {"reply": reply}}]


@pytest.mark.parametrize("bad_content", [None, "debugInfo", 42, ["a"]])
async def test_handle_debug_rejects_non_dict_content(bad_content: Any) -> None:
    """Non-dict ``content`` → bad_params error, session never called."""
    session = _FakeKernelSession()
    websocket = _FakeWebSocket()

    await handle_debug(
        websocket,  # type: ignore[arg-type]
        request_id=3,
        params={"content": bad_content},
        session=session,  # type: ignore[arg-type]
    )

    assert session.requests == []
    assert len(websocket.sent) == 1
    frame = websocket.sent[0]
    assert frame["id"] == 3
    assert frame["error"]["code"] == "bad_params"


async def test_handle_debug_surfaces_session_failure_as_rpc_error() -> None:
    """Timeouts / dead-kernel errors land as a ``debug_failed`` envelope."""
    session = _FakeKernelSession(error=TimeoutError("debug_request 'attach' timed out"))
    websocket = _FakeWebSocket()

    await handle_debug(
        websocket,  # type: ignore[arg-type]
        request_id=11,
        params={"content": {"command": "attach", "arguments": {}}},
        session=session,  # type: ignore[arg-type]
    )

    assert len(websocket.sent) == 1
    frame = websocket.sent[0]
    assert frame["id"] == 11
    assert frame["error"]["code"] == "debug_failed"
    assert "timed out" in frame["error"]["message"]


async def test_debug_event_forwarded_as_dedicated_notify() -> None:
    """iopub ``debug_event`` → ``debug_event`` notify, nothing persisted.

    Debug events carry no ``content_hash`` (their parent message lives
    on the control channel), so the pump must forward them before the
    per-cell routing.  The factory raises on use to prove the
    persistence path is never entered.
    """
    websocket = _FakeWebSocket()
    session = _FakeKernelSession()
    dap_event = {
        "type": "event",
        "seq": 12,
        "event": "stopped",
        "body": {"reason": "breakpoint", "threadId": 1, "allThreadsStopped": True},
    }
    msg = KernelMessage(
        content_hash=None,
        channel="iopub",
        msg_type="debug_event",
        content=dap_event,
        metadata={},
        parent_msg_id="control-msg-id",
    )

    await handle_kernel_message(
        websocket,  # type: ignore[arg-type]
        msg,
        file_path="demo.py",
        session=session,  # type: ignore[arg-type]
        factory=_forbidden_factory,
        pending_run_sources={},
        output_counters={},
        sql_cell_metadata={},
        user={"id": 1, "email": "user@example.com"},  # type: ignore[typeddict-item]
        workspace_id=1,
        cell_run_started_at={},
        channel="iopub",
    )

    assert websocket.sent == [{"notify": "debug_event", "params": {"content": dap_event}}]


async def test_non_debug_messages_still_flow_as_kernel_message() -> None:
    """A plain status frame keeps using the ``kernel_message`` notify."""
    websocket = _FakeWebSocket()
    session = _FakeKernelSession()
    msg = KernelMessage(
        content_hash=None,
        channel="iopub",
        msg_type="status",
        content={"execution_state": "idle"},
        metadata={},
        parent_msg_id=None,
    )

    await handle_kernel_message(
        websocket,  # type: ignore[arg-type]
        msg,
        file_path="demo.py",
        session=session,  # type: ignore[arg-type]
        factory=_forbidden_factory,
        pending_run_sources={},
        output_counters={},
        sql_cell_metadata={},
        user={"id": 1, "email": "user@example.com"},  # type: ignore[typeddict-item]
        workspace_id=1,
        cell_run_started_at={},
        channel="iopub",
    )

    assert len(websocket.sent) == 1
    assert websocket.sent[0]["notify"] == "kernel_message"


@pytest.mark.integration
async def test_debug_request_round_trip_against_real_kernel(tmp_path: Path) -> None:
    """A live ipykernel answers ``debugInfo`` over the control channel.

    Spawns the kernel subprocess, fires one DAP ``debugInfo`` request
    (valid before ``initialize``/``attach``), asserts the reply shape,
    and shuts the kernel down again.
    """
    from pointlessql.services.notebook.kernel_session import KernelSession

    session = KernelSession(
        user_email="debugger-test@example.com",
        notebook_path="debug-demo.py",
        cwd=tmp_path,
    )
    await session.start()
    try:
        reply = await session.debug_request({"command": "debugInfo", "arguments": {}})
        assert reply.get("success") is True
        assert reply.get("command") == "debugInfo"
        body = reply.get("body")
        assert isinstance(body, dict)
        assert "isStarted" in body
    finally:
        await session.shutdown()
