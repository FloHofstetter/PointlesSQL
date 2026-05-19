"""Phase 91 — proposal accept/discard lifecycle tests.

The accept endpoint marks the row + returns the chat session's
``agent_run_id`` so the editor's regular Run path can stamp the
operation against the chat run.  Discard just flips status.
Both fan-out a WS notify on the chat session's broker channel.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, ChatProposal, EditorChatSession


@pytest.fixture
def proposal_row() -> tuple[str, str, str]:
    """Seed a chat session + a pending ``ChatProposal``; cleanup after."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    editor_session_id = f"ed-accept-{uuid.uuid4().hex[:8]}"
    proposal_id = str(uuid.uuid4())
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
        chat = EditorChatSession(
            editor_session_id=editor_session_id,
            workspace_id=1,
            user_id=1,
            agent_run_id=run_id,
            conversation_json="[]",
            turn_count=0,
            created_at=now,
            last_active_at=now,
        )
        session.add(chat)
        session.flush()
        session.add(
            ChatProposal(
                proposal_id=proposal_id,
                chat_session_id=chat.id,
                workspace_id=1,
                sql_text="DELETE FROM main.silver.dupes WHERE id < 10",
                kind="dml",
                rationale="drop sample dupes",
                status="pending",
                created_at=now,
            )
        )
        session.commit()
    yield editor_session_id, run_id, proposal_id
    with factory() as session:
        for prop in (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .all()
        ):
            session.delete(prop)
        chat_row = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .one_or_none()
        )
        if chat_row is not None:
            session.delete(chat_row)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


async def test_accept_returns_sql_and_agent_run(
    admin_client: httpx.AsyncClient,
    proposal_row: tuple[str, str, str],
) -> None:
    """Happy-path: returns the SQL + the chat session's agent_run_id."""
    _, run_id, proposal_id = proposal_row
    response = await admin_client.post(
        f"/api/sql/chat/proposals/{proposal_id}/accept"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sql"].startswith("DELETE")
    assert body["agent_run_id"] == run_id
    assert body["kind"] == "dml"

    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.status == "accepted"
        assert row.accepted_run_id == run_id


async def test_accept_unknown_proposal_returns_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown proposal_id → 404."""
    response = await admin_client.post(
        "/api/sql/chat/proposals/does-not-exist/accept"
    )
    assert response.status_code == 404


async def test_accept_double_accept_returns_409(
    admin_client: httpx.AsyncClient,
    proposal_row: tuple[str, str, str],
) -> None:
    """Accepting twice returns 409 with `already accepted` detail."""
    _, _, proposal_id = proposal_row
    first = await admin_client.post(
        f"/api/sql/chat/proposals/{proposal_id}/accept"
    )
    assert first.status_code == 200
    second = await admin_client.post(
        f"/api/sql/chat/proposals/{proposal_id}/accept"
    )
    assert second.status_code == 409
    assert "accepted" in second.json()["detail"]


async def test_accept_expired_proposal_returns_409(
    admin_client: httpx.AsyncClient,
    proposal_row: tuple[str, str, str],
) -> None:
    """A proposal older than 24h is fenced off + flipped to ``expired``."""
    _, _, proposal_id = proposal_row
    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one()
        )
        row.created_at = datetime.datetime.now(
            datetime.UTC
        ) - datetime.timedelta(days=2)
        session.commit()

    response = await admin_client.post(
        f"/api/sql/chat/proposals/{proposal_id}/accept"
    )
    assert response.status_code == 409
    assert "24 hours" in response.json()["detail"]

    with factory() as session:
        row = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.status == "expired"


async def test_discard_flips_status_and_fanouts(
    admin_client: httpx.AsyncClient,
    proposal_row: tuple[str, str, str],
) -> None:
    """Discard → ``status='discarded'`` + WS notify proposal_discarded."""
    from pointlessql.services.sql_chat import subscribe, unsubscribe

    editor_session_id, _, proposal_id = proposal_row
    queue = subscribe(editor_session_id)
    try:
        response = await admin_client.post(
            f"/api/sql/chat/proposals/{proposal_id}/discard"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "discarded"
        event = queue.get_nowait()
        assert event.kind == "proposal_discarded"
        assert event.payload["proposal_id"] == proposal_id
    finally:
        unsubscribe(editor_session_id, queue)

    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.status == "discarded"


async def test_discard_already_accepted_returns_409(
    admin_client: httpx.AsyncClient,
    proposal_row: tuple[str, str, str],
) -> None:
    """Discarding an already-accepted proposal returns 409."""
    _, _, proposal_id = proposal_row
    await admin_client.post(f"/api/sql/chat/proposals/{proposal_id}/accept")
    response = await admin_client.post(
        f"/api/sql/chat/proposals/{proposal_id}/discard"
    )
    assert response.status_code == 409
