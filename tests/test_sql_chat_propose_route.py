"""``POST /api/sql/chat/{session_id}/propose`` route tests.

The propose route is the LLM's only path to issue non-SELECT SQL:
it writes a :class:`ChatProposal` row and fan-outs a
``proposal_created`` event on the chat broker.  Tests verify:

* Happy path (DML / DDL) creates a row and returns ``proposal_id``.
* SELECT / EXPLAIN is rejected with 400 (the system-prompt routes
  reads through ``pql_query``, not propose).
* Unknown session → 404.
* X-Agent-Run-Id mismatch → 403 (an agent run can only propose into
  the chat session it owns).
* Idempotency: identical SQL within 60s returns the same
  ``proposal_id`` with ``idempotent_match=True``.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, ChatProposal, EditorChatSession


@pytest.fixture
def chat_session_with_run(auth_cookies: dict[str, str]) -> tuple[str, str]:
    """Create a chat session + its owning agent_run; return (session, run)."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    editor_session_id = f"ed-prop-test-{uuid.uuid4().hex[:8]}"
    with factory() as session:
        now = datetime.datetime.now(datetime.UTC)
        session.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id=f"sql-chat-{editor_session_id[:8]}",
                notebook_path="/internal/sql-chat-session",
                status="running",
                started_at=now,
            )
        )
        session.add(
            EditorChatSession(
                editor_session_id=editor_session_id,
                workspace_id=1,
                user_id=1,
                agent_run_id=run_id,
                conversation_json="[]",
                turn_count=0,
                created_at=now,
                last_active_at=now,
            )
        )
        session.commit()
    yield editor_session_id, run_id
    with factory() as session:
        for prop in (
            session.query(ChatProposal)
            .filter(ChatProposal.chat_session_id == _resolve_session_id(session, editor_session_id))
            .all()
        ):
            session.delete(prop)
        for sess in (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .all()
        ):
            session.delete(sess)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def _resolve_session_id(session: Any, editor_session_id: str) -> int:
    """Return chat_session_id by editor_session_id or -1 (already deleted)."""
    row = (
        session.query(EditorChatSession)
        .filter(EditorChatSession.editor_session_id == editor_session_id)
        .one_or_none()
    )
    return row.id if row else -1


async def test_propose_dml_creates_row(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """Happy-path DELETE → proposal row + non-idempotent response."""
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={
            "sql": "DELETE FROM main.silver.dupes WHERE id < 10",
            "rationale": "drop sample dupes",
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "dml"
    assert body["idempotent_match"] is False
    proposal_id = body["proposal_id"]

    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.status == "pending"
        assert row.rationale == "drop sample dupes"


async def test_propose_ddl_classified(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """CREATE SCHEMA classifies as ``ddl``."""
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": "CREATE SCHEMA main.staging"},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "ddl"


async def test_propose_select_rejected(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """SELECT is fenced off — agent must use pql_query instead.

    Returns RFC-9457 422 (ValidationError) post-Phase-91 cleanup.
    """
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": "SELECT 1"},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 422
    assert "pql_query" in response.json()["detail"]


async def test_propose_unknown_session_returns_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Posting to a session that does not exist returns 404."""
    response = await admin_client.post(
        "/api/sql/chat/does-not-exist/propose",
        json={"sql": "DELETE FROM x.y.z WHERE 1=1"},
        headers={"X-Agent-Run-Id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_propose_run_id_mismatch_returns_403(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """Wrong X-Agent-Run-Id is rejected with 403, no row created."""
    editor_session_id, _ = chat_session_with_run
    other_run = str(uuid.uuid4())
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": "DELETE FROM x.y.z WHERE 1=1"},
        headers={"X-Agent-Run-Id": other_run},
    )
    assert response.status_code == 403


async def test_propose_idempotency_within_window(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """Same SQL twice in 60s returns identical proposal_id."""
    editor_session_id, run_id = chat_session_with_run
    sql = "UPDATE main.silver.orders SET status='paid' WHERE id < 5"

    first = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": sql},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert first.status_code == 200
    assert first.json()["idempotent_match"] is False

    second = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": sql},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert second.status_code == 200
    assert second.json()["idempotent_match"] is True
    assert second.json()["proposal_id"] == first.json()["proposal_id"]


async def test_propose_broker_fan_out(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """A WS subscriber receives a ``proposal_created`` event."""
    from pointlessql.services.editor_chat import subscribe, unsubscribe

    editor_session_id, run_id = chat_session_with_run
    queue = subscribe(editor_session_id)
    try:
        response = await admin_client.post(
            f"/api/sql/chat/{editor_session_id}/propose",
            json={"sql": "DELETE FROM main.silver.dupes WHERE 1=1"},
            headers={"X-Agent-Run-Id": run_id},
        )
        assert response.status_code == 200
        # Allow the publish to land — same loop, so a single yield is enough.
        event = queue.get_nowait()
        assert event.kind == "proposal_created"
        assert event.payload["proposal_id"] == response.json()["proposal_id"]
        assert event.payload["kind"] == "dml"
    finally:
        unsubscribe(editor_session_id, queue)


# ---------------------------------------------------------------------------
# typed body validation
# ---------------------------------------------------------------------------


async def test_propose_sql_text_alias_still_accepted(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """The legacy ``sql_text`` field-name keeps working post-Pydantic refactor.

    Earlier plugin clients posted ``{"sql_text": "..."}``; Phase 106.5
    moved the body off ``dict[str, Any]`` and onto :class:`ProposeSqlBody`,
    which coalesces ``sql_text`` into ``sql`` at validation time so we
    don't break the existing wire contract.
    """
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql_text": "DELETE FROM main.silver.dupes WHERE 1=1"},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "dml"
    assert body["idempotent_match"] is False


async def test_propose_sql_missing_required_is_422(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """Empty body (no sql / sql_text) → 422 with field name surfaced."""
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"rationale": "trying something"},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 422
    assert "sql is required" in response.text


async def test_propose_sql_blank_string_is_422(
    admin_client: httpx.AsyncClient,
    chat_session_with_run: tuple[str, str],
) -> None:
    """Whitespace-only ``sql`` is rejected — agents must send a real statement."""
    editor_session_id, run_id = chat_session_with_run
    response = await admin_client.post(
        f"/api/sql/chat/{editor_session_id}/propose",
        json={"sql": "   \n  "},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert response.status_code == 422
