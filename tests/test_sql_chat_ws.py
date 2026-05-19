"""Phase 91 — smoke tests for ``/ws/sql/chat/{editor_session_id}``.

We never start a real ``hermes_agent`` process; a ``FakeAIAgent``
factory is injected via :func:`build_agent`-monkeypatch so the
WS layer is exercised end-to-end (auth, ready frame, prompt
round-trip, cancel) without touching an LLM provider.
"""

from __future__ import annotations

import json
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
            self._on_token(None)  # tool-phase sentinel
        return {
            "final_response": self._reply,
            "messages": [{"role": "assistant", "content": self._reply}],
            "api_calls": 1,
        }


@pytest.fixture
def fake_agent_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace :func:`build_agent` with a :class:`_FakeAIAgent` factory."""

    def fake_build_agent(*, on_token: Any, **_: Any) -> _FakeAIAgent:
        return _FakeAIAgent(
            reply="The top countries are DE, FR, US.",
            emit_tokens=("The ", "top ", "countries..."),
            stream_delta_callback=on_token,
        )

    monkeypatch.setattr(
        "pointlessql.services.sql_chat._agent_factory.build_agent",
        fake_build_agent,
    )
    # Bypass the env-var check so the WS-open path succeeds even
    # on a host without a real LLM key.
    monkeypatch.setattr(
        "pointlessql.api.sql_chat_ws.check_llm_configured",
        lambda: True,
    )


@pytest.fixture
def fresh_session_id() -> str:
    """Return a unique ``editor_session_id`` per test."""
    return f"ed-ws-{uuid.uuid4().hex[:12]}"


def _cleanup(editor_session_id: str) -> None:
    """Drop the chat session + its agent_run after the test."""
    from pointlessql.models import ChatProposal

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
            session.query(ChatProposal)
            .filter(ChatProposal.chat_session_id == chat_row.id)
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
                    f"/ws/sql/chat/{fresh_session_id}"
                ) as ws:
                    ws.receive_text()
        assert exc_info.value.code == 4401
    finally:
        _cleanup(fresh_session_id)


def test_ws_llm_unconfigured_closes_with_1011(
    monkeypatch: pytest.MonkeyPatch,
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """Authenticated but no LLM env var → close 1011 + reason."""
    monkeypatch.setattr(
        "pointlessql.api.sql_chat_ws.check_llm_configured",
        lambda: False,
    )
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(
                    f"/ws/sql/chat/{fresh_session_id}"
                ) as ws:
                    ws.receive_text()
        assert exc_info.value.code == 1011
    finally:
        _cleanup(fresh_session_id)


def test_ws_ready_frame_includes_agent_run(
    fake_agent_factory: None,
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """Server emits ``ready`` with ``agent_run_id`` + empty history."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{fresh_session_id}"
            ) as ws:
                frame = json.loads(ws.receive_text())
        assert frame["notify"] == "ready"
        assert frame["params"]["history"] == []
        assert frame["params"]["agent_run_id"]
    finally:
        _cleanup(fresh_session_id)


def test_ws_prompt_round_trip(
    fake_agent_factory: None,
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """``prompt`` → tokens + ``final`` notify + reply."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{fresh_session_id}"
            ) as ws:
                ready = json.loads(ws.receive_text())
                assert ready["notify"] == "ready"
                ws.send_text(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "prompt",
                            "params": {"text": "top countries please"},
                        }
                    )
                )
                # Collect frames until ``final``.
                tokens: list[str] = []
                final: dict[str, Any] | None = None
                reply: dict[str, Any] | None = None
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if "result" in msg:
                        reply = msg
                    elif msg.get("notify") == "token":
                        tokens.append(msg["params"]["text"])
                    elif msg.get("notify") == "final":
                        final = msg
                        break
        assert reply is not None
        assert reply["result"]["agent_run_id"]
        assert final is not None
        assert final["params"]["text"].startswith("The top")
        assert "".join(tokens).startswith("The top")
    finally:
        _cleanup(fresh_session_id)


def test_ws_reset_clears_history(
    fake_agent_factory: None,
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """``reset`` truncates conversation_json; next prompt sees empty history."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{fresh_session_id}"
            ) as ws:
                _ready = ws.receive_text()
                ws.send_text(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "prompt",
                            "params": {"text": "first prompt"},
                        }
                    )
                )
                # Drain frames until ``final``.
                for _ in range(20):
                    if json.loads(ws.receive_text()).get("notify") == "final":
                        break
                ws.send_text(json.dumps({"id": 2, "method": "reset"}))
                reset_reply = json.loads(ws.receive_text())
        assert reset_reply["result"]["reset"] is True
        factory = app.state.session_factory
        with factory() as session:
            row = (
                session.query(EditorChatSession)
                .filter(
                    EditorChatSession.editor_session_id == fresh_session_id
                )
                .one()
            )
            assert row.conversation_json == "[]"
            assert row.turn_count == 0
    finally:
        _cleanup(fresh_session_id)


def test_ws_unknown_method_returns_error(
    fake_agent_factory: None,
    auth_cookies: dict[str, str],
    fresh_session_id: str,
) -> None:
    """Bad method → ``{"id": ..., "error": {...}}`` envelope."""
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{fresh_session_id}"
            ) as ws:
                _ready = ws.receive_text()
                ws.send_text(
                    json.dumps({"id": 7, "method": "nope"})
                )
                err = json.loads(ws.receive_text())
        assert err["id"] == 7
        assert err["error"]["code"] == "unknown_method"
    finally:
        _cleanup(fresh_session_id)
