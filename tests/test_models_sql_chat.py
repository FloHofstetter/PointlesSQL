"""EditorChatSession + ChatProposal model round-trips.

Smoke-tests that the two ORM models map cleanly to the
``q5s7u9w1y3a5`` migration: column types, unique constraints, the
two CHECK constraints on ``chat_proposals``, and the
JSON-as-text round-trip for ``conversation_json``.

Route + service tests for the WS surface live in
``test_sql_chat_ws.py`` and ``test_sql_chat_session.py``; these are
schema-level only.
"""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    ChatProposal,
    EditorChatSession,
)


def _make_agent_run(run_id: str | None = None) -> AgentRun:
    return AgentRun(
        id=run_id or str(uuid.uuid4()),
        principal="sql-chat-test",
        agent_id=f"sql-chat-{(run_id or 'abc')[:8]}",
        notebook_path="/internal/sql-chat-session",
        status="running",
        started_at=datetime.datetime.now(datetime.UTC),
    )


def _make_session(
    *,
    user_id: int,
    agent_run_id: str,
    editor_session_id: str | None = None,
    workspace_id: int = 1,
) -> EditorChatSession:
    now = datetime.datetime.now(datetime.UTC)
    return EditorChatSession(
        editor_session_id=editor_session_id or str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=user_id,
        agent_run_id=agent_run_id,
        conversation_json="[]",
        turn_count=0,
        created_at=now,
        last_active_at=now,
    )


def _make_proposal(
    *,
    chat_session_id: int,
    proposal_id: str | None = None,
    kind: str = "dml",
    status: str = "pending",
    workspace_id: int = 1,
) -> ChatProposal:
    now = datetime.datetime.now(datetime.UTC)
    return ChatProposal(
        proposal_id=proposal_id or str(uuid.uuid4()),
        chat_session_id=chat_session_id,
        workspace_id=workspace_id,
        sql_text="DELETE FROM main.stage.dupes WHERE id < 10",
        kind=kind,
        rationale="Drop sample duplicates",
        status=status,
        created_at=now,
    )


def test_editor_chat_session_round_trip() -> None:
    """Insert + read recovers every column verbatim, conversation_json JSON-stable."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    convo = [
        {"role": "system", "content": "you are a SQL assistant"},
        {"role": "user", "content": "show me top countries"},
    ]
    with factory() as session:
        session.add(_make_agent_run(run_id))
        chat_session = _make_session(
            user_id=1,
            agent_run_id=run_id,
            editor_session_id="ed-session-rt-1",
        )
        chat_session.conversation_json = json.dumps(convo)
        chat_session.turn_count = 2
        chat_session.current_turn_id = "turn-7"
        session.add(chat_session)
        session.commit()
        sid = chat_session.id

    try:
        with factory() as session:
            loaded = session.get(EditorChatSession, sid)
            assert loaded is not None
            assert loaded.editor_session_id == "ed-session-rt-1"
            assert loaded.workspace_id == 1
            assert loaded.user_id == 1
            assert loaded.agent_run_id == run_id
            assert json.loads(loaded.conversation_json) == convo
            assert loaded.turn_count == 2
            assert loaded.current_turn_id == "turn-7"
    finally:
        _cleanup_session(sid, run_id)


def test_editor_chat_session_editor_id_unique() -> None:
    """Two sessions with the same editor_session_id violate UNIQUE."""
    factory = app.state.session_factory
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_a))
        session.add(_make_agent_run(run_b))
        session.add(
            _make_session(
                user_id=1,
                agent_run_id=run_a,
                editor_session_id="ed-session-dup",
            )
        )
        session.commit()

    with factory() as session:
        session.add(
            _make_session(
                user_id=1,
                agent_run_id=run_b,
                editor_session_id="ed-session-dup",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with factory() as session:
        for sess in session.query(EditorChatSession).filter(
            EditorChatSession.editor_session_id == "ed-session-dup"
        ).all():
            session.delete(sess)
        for run in (
            session.get(AgentRun, run_a),
            session.get(AgentRun, run_b),
        ):
            if run is not None:
                session.delete(run)
        session.commit()


def test_editor_chat_session_agent_run_unique() -> None:
    """One agent_run can back at most one chat-session (1:1 FK)."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_id))
        session.add(
            _make_session(
                user_id=1,
                agent_run_id=run_id,
                editor_session_id="ed-session-1to1-a",
            )
        )
        session.commit()

    with factory() as session:
        session.add(
            _make_session(
                user_id=1,
                agent_run_id=run_id,
                editor_session_id="ed-session-1to1-b",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with factory() as session:
        for sess in session.query(EditorChatSession).filter(
            EditorChatSession.agent_run_id == run_id
        ).all():
            session.delete(sess)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def test_chat_proposal_round_trip() -> None:
    """ChatProposal persists kind/status/SQL verbatim."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_id))
        chat_session = _make_session(
            user_id=1,
            agent_run_id=run_id,
            editor_session_id="ed-session-prop-rt",
        )
        session.add(chat_session)
        session.flush()
        proposal = _make_proposal(chat_session_id=chat_session.id)
        session.add(proposal)
        session.commit()
        pid = proposal.id
        sid = chat_session.id

    try:
        with factory() as session:
            loaded = session.get(ChatProposal, pid)
            assert loaded is not None
            assert loaded.chat_session_id == sid
            assert loaded.kind == "dml"
            assert loaded.status == "pending"
            assert "DELETE" in loaded.sql_text
            assert loaded.accepted_at is None
            assert loaded.accepted_run_id is None
    finally:
        _cleanup_session(sid, run_id)


@pytest.mark.parametrize("bad_kind", ["select", "explain", "", "DDL"])
def test_chat_proposal_kind_check(bad_kind: str) -> None:
    """``kind`` outside ``{'dml', 'ddl'}`` violates CHECK."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_id))
        chat_session = _make_session(
            user_id=1,
            agent_run_id=run_id,
            editor_session_id=f"ed-session-bad-kind-{bad_kind}",
        )
        session.add(chat_session)
        session.flush()
        session.add(
            _make_proposal(chat_session_id=chat_session.id, kind=bad_kind)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with factory() as session:
        sess = (
            session.query(EditorChatSession)
            .filter(
                EditorChatSession.editor_session_id
                == f"ed-session-bad-kind-{bad_kind}"
            )
            .one_or_none()
        )
        if sess is not None:
            session.delete(sess)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


@pytest.mark.parametrize("bad_status", ["new", "running", "", "ACCEPTED"])
def test_chat_proposal_status_check(bad_status: str) -> None:
    """``status`` outside the 4-value allowlist violates CHECK."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_id))
        chat_session = _make_session(
            user_id=1,
            agent_run_id=run_id,
            editor_session_id=f"ed-session-bad-status-{bad_status}",
        )
        session.add(chat_session)
        session.flush()
        session.add(
            _make_proposal(
                chat_session_id=chat_session.id, status=bad_status
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with factory() as session:
        sess = (
            session.query(EditorChatSession)
            .filter(
                EditorChatSession.editor_session_id
                == f"ed-session-bad-status-{bad_status}"
            )
            .one_or_none()
        )
        if sess is not None:
            session.delete(sess)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def test_chat_proposal_unique_proposal_id() -> None:
    """Two proposals sharing ``proposal_id`` violate UNIQUE."""
    factory = app.state.session_factory
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    proposal_uuid = str(uuid.uuid4())
    with factory() as session:
        session.add(_make_agent_run(run_a))
        session.add(_make_agent_run(run_b))
        sa = _make_session(
            user_id=1, agent_run_id=run_a, editor_session_id="ed-prop-dup-a"
        )
        sb = _make_session(
            user_id=1, agent_run_id=run_b, editor_session_id="ed-prop-dup-b"
        )
        session.add(sa)
        session.add(sb)
        session.flush()
        session.add(
            _make_proposal(chat_session_id=sa.id, proposal_id=proposal_uuid)
        )
        session.commit()
        sa_id = sa.id
        sb_id = sb.id

    with factory() as session:
        session.add(
            _make_proposal(chat_session_id=sb_id, proposal_id=proposal_uuid)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with factory() as session:
        for prop in (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_uuid)
            .all()
        ):
            session.delete(prop)
        for sid in (sa_id, sb_id):
            sess = session.get(EditorChatSession, sid)
            if sess is not None:
                session.delete(sess)
        for rid in (run_a, run_b):
            run = session.get(AgentRun, rid)
            if run is not None:
                session.delete(run)
        session.commit()


def _cleanup_session(session_id: int, run_id: str) -> None:
    """Drop the test session row + every proposal + the parent run."""
    factory = app.state.session_factory
    with factory() as session:
        for prop in (
            session.query(ChatProposal)
            .filter(ChatProposal.chat_session_id == session_id)
            .all()
        ):
            session.delete(prop)
        sess = session.get(EditorChatSession, session_id)
        if sess is not None:
            session.delete(sess)
        run = session.get(AgentRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()
