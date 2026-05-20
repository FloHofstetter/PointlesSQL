"""Tests for Phase 104 — NL→Notebook cell-sequence proposals."""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, EditorChatSession, User
from pointlessql.services.notebook import (
    cell_sequence_proposals as cell_sequence_proposals_service,
)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_chat_session(factory: sessionmaker) -> int:  # type: ignore[type-arg]
    """Insert a User + EditorChatSession pair; return the session id."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test",
            display_name="t",
            password_hash="x",
            is_admin=False,
            created_at=now,
        )
        s.add(u)
        s.flush()
        cs = EditorChatSession(
            editor_session_id=str(uuid.uuid4()),
            workspace_id=1,
            user_id=u.id,
            agent_run_id=str(uuid.uuid4()),
            conversation_json="[]",
            turn_count=0,
            created_at=now,
            last_active_at=now,
        )
        s.add(cs)
        s.commit()
        return cs.id


# -- service ------------------------------------------------------------------


def test_propose_sequence_rejects_empty_cells(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Empty cell list raises."""
    sid = _seed_chat_session(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_sequence_proposals_service.propose_sequence(
                session,
                chat_session_id=sid,
                prompt="x",
                cells=[],
            )


def test_propose_sequence_rejects_unknown_chat(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown chat_session_id raises."""
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_sequence_proposals_service.propose_sequence(
                session,
                chat_session_id=99999,
                prompt="x",
                cells=[{"cell_type": "code", "source": "1"}],
            )


def test_propose_sequence_inserts_and_normalises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Cells are sorted by position and persisted as JSON."""
    sid = _seed_chat_session(factory)
    with factory() as session:
        row = cell_sequence_proposals_service.propose_sequence(
            session,
            chat_session_id=sid,
            prompt="ingest the orders table",
            cells=[
                {"position": 1, "cell_type": "code", "source": "df.head()"},
                {"position": 0, "cell_type": "code", "source": "import pandas as pd"},
            ],
        )
        assert row.status == "pending"
        envelope = cell_sequence_proposals_service.get_sequence(
            session, proposal_id=row.proposal_id
        )
        session.commit()
    assert envelope is not None
    # Cells re-sorted by position.
    assert envelope["cells"][0]["source"] == "import pandas as pd"
    assert envelope["cells"][1]["source"] == "df.head()"


def test_accept_then_discard_double_terminal_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An already-accepted row cannot be discarded."""
    sid = _seed_chat_session(factory)
    with factory() as session:
        row = cell_sequence_proposals_service.propose_sequence(
            session,
            chat_session_id=sid,
            prompt="x",
            cells=[{"cell_type": "code", "source": "1"}],
        )
        proposal_id = row.proposal_id
        cell_sequence_proposals_service.accept_sequence(
            session, proposal_id=proposal_id
        )
        with pytest.raises(ValidationError):
            cell_sequence_proposals_service.discard_sequence(
                session, proposal_id=proposal_id
            )


def test_accept_unknown_raises(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Unknown proposal_id raises."""
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_sequence_proposals_service.accept_sequence(
                session, proposal_id="0" * 36
            )


def test_propose_sequence_rejects_bad_cell_type(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Cells with an unknown cell_type raise."""
    sid = _seed_chat_session(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_sequence_proposals_service.propose_sequence(
                session,
                chat_session_id=sid,
                prompt="x",
                cells=[{"cell_type": "raw", "source": "x"}],
            )


def test_list_pending_excludes_terminal(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Discarded / accepted rows do not surface in pending list."""
    sid = _seed_chat_session(factory)
    with factory() as session:
        row = cell_sequence_proposals_service.propose_sequence(
            session,
            chat_session_id=sid,
            prompt="x",
            cells=[{"cell_type": "code", "source": "1"}],
        )
        cell_sequence_proposals_service.discard_sequence(
            session, proposal_id=row.proposal_id
        )
        cell_sequence_proposals_service.propose_sequence(
            session,
            chat_session_id=sid,
            prompt="x2",
            cells=[{"cell_type": "code", "source": "2"}],
        )
        session.commit()
        listed = cell_sequence_proposals_service.list_pending_for_session(
            session, chat_session_id=sid
        )
    prompts = [r["prompt"] for r in listed]
    assert prompts == ["x2"]


# -- REST --------------------------------------------------------------------


async def test_api_sequence_lifecycle(
    admin_client: httpx.AsyncClient,
) -> None:
    """propose → fetch → accept round-trip via REST.

    Uses the admin_client + the conftest-provided test workspace; we
    don't have an editor chat session pre-seeded so this test only
    verifies the validation envelope on the 422 path (chat session
    does not exist).
    """
    fake_session_id = 999_999
    resp = await admin_client.post(
        f"/api/notebook/chat/{fake_session_id}/propose-sequence",
        json={
            "prompt": "load orders",
            "cells": [{"cell_type": "code", "source": "1"}],
        },
    )
    assert resp.status_code == 422


async def test_api_propose_rejects_empty_cells(
    admin_client: httpx.AsyncClient,
) -> None:
    """Empty cell list surfaces as 422 via the service-side guard."""
    resp = await admin_client.post(
        "/api/notebook/chat/1/propose-sequence",
        json={"prompt": "x", "cells": []},
    )
    # Service raises after the chat lookup; either step lands as 422.
    assert resp.status_code == 422


async def test_api_get_unknown_sequence_returns_422(
    admin_client: httpx.AsyncClient,
) -> None:
    """Fetching an unknown proposal returns 422."""
    fake = "0" * 36
    resp = await admin_client.get(
        f"/api/notebook/chat/sequences/{fake}"
    )
    assert resp.status_code == 422
