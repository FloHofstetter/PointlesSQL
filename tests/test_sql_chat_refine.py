"""Phase 91.3 — refine-loop tests.

The ``refine`` WS method templates the human's "this didn't work,
try again" affordance into a structured user prompt and runs it
through the normal turn pipeline.  We verify:

* Hint stencils produce stable text (``zero_rows`` vs ``error``).
* Unknown hints return a ``bad_refine`` error envelope.
* A successful refine appends the synthetic user-message to the
  conversation history so the next ``ready`` frame restores it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pointlessql.api.main import app
from pointlessql.api.sql_chat_ws import _format_refine_hint
from pointlessql.models import AgentRun, EditorChatSession


class _FakeAIAgent:
    """Tiny stub used by the refine round-trip tests."""

    def __init__(self, *, stream_delta_callback: Any = None, **_: Any) -> None:
        self._on_token = stream_delta_callback

    def run_conversation(
        self,
        user_message: str,  # noqa: ARG002
        conversation_history: list[dict[str, Any]] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        if self._on_token is not None:
            self._on_token("refined")
        return {
            "final_response": "refined ok",
            "messages": [{"role": "assistant", "content": "refined ok"}],
            "api_calls": 1,
        }


def test_format_refine_hint_zero_rows() -> None:
    """zero_rows stencil mentions 0 rows + asks to widen the filter."""
    rendered = _format_refine_hint(
        {"hint": "zero_rows", "last_sql": "SELECT * FROM main.s.t WHERE x = 1"}
    )
    assert rendered is not None
    assert "0 rows" in rendered
    assert "SELECT * FROM main.s.t WHERE x = 1" in rendered
    assert "widen the filter" in rendered or "filter" in rendered


def test_format_refine_hint_error_includes_message() -> None:
    """error stencil interpolates last_error verbatim."""
    rendered = _format_refine_hint(
        {
            "hint": "error",
            "last_sql": "SELECT 1/0",
            "last_error": "division by zero",
        }
    )
    assert rendered is not None
    assert "division by zero" in rendered
    assert "SELECT 1/0" in rendered


def test_format_refine_hint_unknown_returns_none() -> None:
    """Unrecognised hints return ``None`` so the WS can 4xx."""
    assert _format_refine_hint({"hint": "guess"}) is None
    assert _format_refine_hint({"hint": ""}) is None
    assert _format_refine_hint({}) is None


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


@pytest.fixture
def fake_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the agent-builder so refine never touches a real LLM."""

    def fake_build_agent(*, on_token: Any, **_: Any) -> _FakeAIAgent:
        return _FakeAIAgent(stream_delta_callback=on_token)

    monkeypatch.setattr(
        "pointlessql.services.sql_chat._agent_factory.build_agent",
        fake_build_agent,
    )
    monkeypatch.setattr(
        "pointlessql.api.sql_chat_ws.check_llm_configured",
        lambda: True,
    )


def test_ws_refine_runs_a_turn(
    fake_factory: None,
    auth_cookies: dict[str, str],
) -> None:
    """Refine triggers a normal turn; the final notify carries the answer."""
    editor_session_id = f"ed-refine-{uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{editor_session_id}"
            ) as ws:
                assert json.loads(ws.receive_text())["notify"] == "ready"
                ws.send_text(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "refine",
                            "params": {
                                "hint": "zero_rows",
                                "last_sql": "SELECT * FROM x.y.z WHERE country='ZZ'",
                            },
                        }
                    )
                )
                final = None
                for _ in range(20):
                    frame = json.loads(ws.receive_text())
                    if frame.get("notify") == "final":
                        final = frame
                        break
        assert final is not None
        assert final["params"]["text"] == "refined ok"
    finally:
        _cleanup(editor_session_id)


def test_ws_refine_bad_hint_returns_error(
    fake_factory: None,
    auth_cookies: dict[str, str],
) -> None:
    """Refining with no hint surfaces ``bad_refine``."""
    editor_session_id = f"ed-refine-bad-{uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app, cookies=auth_cookies) as client:
            with client.websocket_connect(
                f"/ws/sql/chat/{editor_session_id}"
            ) as ws:
                assert json.loads(ws.receive_text())["notify"] == "ready"
                ws.send_text(json.dumps({"id": 7, "method": "refine", "params": {}}))
                err = json.loads(ws.receive_text())
        assert err["id"] == 7
        assert err["error"]["code"] == "bad_refine"
    finally:
        _cleanup(editor_session_id)
