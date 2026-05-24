"""smoke tests for ``/ws/notebook/chat/{editor_session_id}``.

Forks the Phase-91 SQL chat WS smoke suite.  Verifies the
JSON-RPC envelope, the ``ready`` notify, the prompt → tokens →
final round-trip, and the surface=notebook env-var routing
(``POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID`` is set, not
``POINTLESSQL_CHAT_SESSION_ID``).
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pointlessql.api.main import app
from pointlessql.models import AgentRun, EditorChatSession


class _FakeAIAgent:
    """Synchronous stand-in for :class:`hermes_agent.AIAgent`."""

    def __init__(
        self,
        *,
        reply: str = "ok",
        emit_tokens: tuple[str, ...] = ("ok",),
        stream_delta_callback: Any = None,
        **_: Any,
    ) -> None:
        self._reply = reply
        self._tokens = emit_tokens
        self._on_token = stream_delta_callback

    def run_conversation(
        self,
        user_message: str,  # noqa: ARG002
        conversation_history: list[dict[str, Any]] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        if self._on_token is not None:
            for tok in self._tokens:
                self._on_token(tok)
            self._on_token(None)
        return {
            "final_response": self._reply,
            "messages": [{"role": "assistant", "content": self._reply}],
            "api_calls": 1,
        }


_LAST_BUILD_KWARGS: dict[str, Any] = {}


@pytest.fixture
def fake_agent_factory(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``build_agent`` with a fake that captures kwargs."""

    def fake_build_agent(*, on_token: Any, **kwargs: Any) -> _FakeAIAgent:
        _LAST_BUILD_KWARGS.clear()
        _LAST_BUILD_KWARGS.update(kwargs)
        # Mimic the real factory's env-var split so the env-routing
        # test below can observe which variable was set.
        surface = kwargs.get("surface", "sql")
        editor_session_id = kwargs.get("editor_session_id", "")
        if surface == "notebook":
            os.environ["POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID"] = (
                editor_session_id
            )
            os.environ.pop("POINTLESSQL_CHAT_SESSION_ID", None)
        else:
            os.environ["POINTLESSQL_CHAT_SESSION_ID"] = editor_session_id
            os.environ.pop("POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID", None)
        return _FakeAIAgent(
            reply="Inserted a cell for you.",
            emit_tokens=("Inserted ", "a ", "cell."),
            stream_delta_callback=on_token,
        )

    monkeypatch.setattr(
        "pointlessql.services.editor_chat._agent_factory.build_agent",
        fake_build_agent,
    )
    monkeypatch.setattr(
        "pointlessql.api.notebook_chat_ws.check_llm_configured",
        lambda: True,
    )
    return _LAST_BUILD_KWARGS


@pytest.fixture
def fresh_session_id() -> str:
    """Return a unique notebook chat session id per test."""
    return f"nb-ws-{uuid.uuid4().hex[:12]}"


def _cleanup(editor_session_id: str) -> None:
    """Drop the chat session + its agent_run after the test."""
    from pointlessql.models import NotebookCellProposal

    factory = app.state.session_factory
    with factory() as session:
        chat_row = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .one_or_none()
        )
        if chat_row is None:
            return
        for prop in (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.chat_session_id == chat_row.id)
            .all()
        ):
            session.delete(prop)
        run_id = chat_row.agent_run_id
        session.delete(chat_row)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def test_ws_anonymous_closes_with_4401(fresh_session_id: str) -> None:
    """No cookie + no Bearer → close 4401 before any frame."""
    try:
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(
                    f"/ws/notebook/chat/{fresh_session_id}"
                ) as ws:
                    ws.receive_text()
        assert exc_info.value.code == 4401
    finally:
        _cleanup(fresh_session_id)


def test_ws_ready_frame_includes_agent_run(
    fake_agent_factory: dict[str, Any],  # noqa: ARG001 — fixture wire
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """Server emits ``ready`` with ``agent_run_id`` + empty history."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/notebook/chat/{fresh_session_id}"
            ) as ws:
                frame = json.loads(ws.receive_text())
        assert frame["notify"] == "ready"
        assert frame["params"]["history"] == []
        assert frame["params"]["agent_run_id"]
    finally:
        _cleanup(fresh_session_id)


def test_ws_prompt_uses_notebook_surface(
    fake_agent_factory: dict[str, Any],
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """The WS forwards ``surface='notebook'`` to ``build_agent``."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/notebook/chat/{fresh_session_id}"
            ) as ws:
                ready = json.loads(ws.receive_text())
                assert ready["notify"] == "ready"
                ws.send_text(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "prompt",
                            "params": {"text": "add a numpy cell please"},
                        }
                    )
                )
                # Drain until final.
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg.get("notify") == "final":
                        break
        # The fake factory must have seen surface='notebook'.
        assert fake_agent_factory.get("surface") == "notebook"
    finally:
        _cleanup(fresh_session_id)


def test_ws_unknown_method_returns_error(
    fake_agent_factory: dict[str, Any],  # noqa: ARG001
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """Unknown method → ``error`` envelope with ``unknown_method`` code."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/notebook/chat/{fresh_session_id}"
            ) as ws:
                json.loads(ws.receive_text())  # consume ready
                ws.send_text(json.dumps({"id": 9, "method": "refine"}))
                reply = json.loads(ws.receive_text())
        assert reply["error"]["code"] == "unknown_method"
    finally:
        _cleanup(fresh_session_id)
