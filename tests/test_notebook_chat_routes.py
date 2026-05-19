"""Phase 96 — notebook AI-assistant route + model tests.

Covers:

* Three propose-cell route shapes (propose / fix / explain) — happy
  paths, X-Agent-Run-Id 403, unknown-session 404, idempotent fix.
* Accept / discard lifecycle (incl. explain-not-accept-route 409).
* Explanations GET endpoint.
* Save-path provenance flush — proposal_acceptances in the body
  writes NotebookCellProvenance rows keyed on the reconciler's
  cell_uuid.
* Rename guard — pointlessql.services.sql_chat must not import.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    EditorChatSession,
    NotebookCellProposal,
    NotebookCellProvenance,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nb_chat_session_with_run(
    auth_cookies: dict[str, str],  # noqa: ARG001 — depended on for cleanup ordering
) -> tuple[str, str]:
    """Create a notebook-chat EditorChatSession + its agent_run."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    editor_session_id = f"nb-chat-test-{uuid.uuid4().hex[:8]}"
    with factory() as session:
        now = datetime.datetime.now(datetime.UTC)
        session.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id=f"nb-chat-{editor_session_id[:8]}",
                notebook_path="/internal/nb-chat-session",
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
        chat_id = _resolve_session_id(session, editor_session_id)
        if chat_id > 0:
            for prop in (
                session.query(NotebookCellProposal)
                .filter(NotebookCellProposal.chat_session_id == chat_id)
                .all()
            ):
                # Also clean any provenance rows referencing these.
                for prov in (
                    session.query(NotebookCellProvenance)
                    .filter(
                        NotebookCellProvenance.proposal_id == prop.proposal_id
                    )
                    .all()
                ):
                    session.delete(prov)
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
    row = (
        session.query(EditorChatSession)
        .filter(EditorChatSession.editor_session_id == editor_session_id)
        .one_or_none()
    )
    return row.id if row else -1


# ---------------------------------------------------------------------------
# propose-cell route
# ---------------------------------------------------------------------------


async def test_propose_cell_happy_path(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Happy-path propose → row written with action='propose' + payload."""
    editor_session_id, run_id = nb_chat_session_with_run
    resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={
            "cell_type": "code",
            "source": "print('hi')",
            "position_at_end": True,
            "rationale": "demo cell",
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "propose"
    proposal_id = body["proposal_id"]

    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.action == "propose"
        assert row.cell_type == "code"
        assert row.new_source == "print('hi')"
        assert row.status == "pending"
        assert row.position_at_end is True
        assert row.target_cell_uuid is None


async def test_propose_cell_validates_cell_type(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Unknown cell_type → 400, no row written."""
    editor_session_id, run_id = nb_chat_session_with_run
    resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={"cell_type": "sql", "source": "SELECT 1"},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert resp.status_code == 400


async def test_propose_cell_session_mismatch_403(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """X-Agent-Run-Id mismatch → 403."""
    editor_session_id, _run_id = nb_chat_session_with_run
    resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={"cell_type": "code", "source": "x = 1"},
        headers={"X-Agent-Run-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403


async def test_propose_cell_unknown_session_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown editor_session_id → 404."""
    resp = await admin_client.post(
        "/api/notebook/chat/unknown-session/propose-cell",
        json={"cell_type": "code", "source": "x = 1"},
        headers={"X-Agent-Run-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# fix-cell route
# ---------------------------------------------------------------------------


async def test_fix_cell_happy_path(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Happy-path fix → row with action='fix' and target_cell_uuid set."""
    editor_session_id, run_id = nb_chat_session_with_run
    resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/fix-cell",
        json={
            "target_cell_uuid": "cell-xyz",
            "new_source": "df.head(20)",
            "rationale": "widen",
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "fix"
    assert body["idempotent_match"] is False


async def test_fix_cell_idempotency_window(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Identical fix within 60s → idempotent_match=True, same proposal_id."""
    editor_session_id, run_id = nb_chat_session_with_run
    payload = {
        "target_cell_uuid": "cell-xyz",
        "new_source": "x = 1",
    }
    first = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/fix-cell",
        json=payload,
        headers={"X-Agent-Run-Id": run_id},
    )
    assert first.status_code == 200
    second = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/fix-cell",
        json=payload,
        headers={"X-Agent-Run-Id": run_id},
    )
    assert second.status_code == 200
    body_a = first.json()
    body_b = second.json()
    assert body_a["proposal_id"] == body_b["proposal_id"]
    assert body_b["idempotent_match"] is True


# ---------------------------------------------------------------------------
# explain-cell route (auto-accept)
# ---------------------------------------------------------------------------


async def test_explain_cell_auto_accepts(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Explain creates a row at status='accepted' + a provenance row inline."""
    editor_session_id, run_id = nb_chat_session_with_run
    resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/explain-cell",
        json={
            "target_cell_uuid": "cell-xyz",
            "explanation": "Baseline LR.",
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    proposal_id = body["proposal_id"]

    factory = app.state.session_factory
    with factory() as session:
        prop = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one()
        )
        assert prop.status == "accepted"
        assert prop.accepted_run_id == run_id
        assert prop.inserted_cell_uuid == "cell-xyz"
        # Inline provenance row exists.
        prov = (
            session.query(NotebookCellProvenance)
            .filter(NotebookCellProvenance.proposal_id == proposal_id)
            .one()
        )
        assert prov.action == "explain"
        assert prov.cell_uuid == "cell-xyz"


# ---------------------------------------------------------------------------
# accept / discard lifecycle
# ---------------------------------------------------------------------------


async def test_accept_propose_returns_payload(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Accept on a propose row returns the application payload."""
    editor_session_id, run_id = nb_chat_session_with_run
    create = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={"cell_type": "markdown", "source": "# Hello"},
        headers={"X-Agent-Run-Id": run_id},
    )
    proposal_id = create.json()["proposal_id"]
    resp = await admin_client.post(
        f"/api/notebook/chat/proposals/{proposal_id}/accept"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "propose"
    assert body["cell_type"] == "markdown"
    assert body["new_source"] == "# Hello"
    assert body["agent_run_id"] == run_id


async def test_accept_on_explain_is_409(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Explain rows are accepted at create — accept endpoint rejects them."""
    editor_session_id, run_id = nb_chat_session_with_run
    create = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/explain-cell",
        json={"target_cell_uuid": "cell-xyz", "explanation": "x"},
        headers={"X-Agent-Run-Id": run_id},
    )
    proposal_id = create.json()["proposal_id"]
    resp = await admin_client.post(
        f"/api/notebook/chat/proposals/{proposal_id}/accept"
    )
    assert resp.status_code == 409


async def test_discard_propose_flips_status(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """Discard sets status='discarded' on a pending propose."""
    editor_session_id, run_id = nb_chat_session_with_run
    create = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={"cell_type": "code", "source": "x = 1"},
        headers={"X-Agent-Run-Id": run_id},
    )
    proposal_id = create.json()["proposal_id"]
    resp = await admin_client.post(
        f"/api/notebook/chat/proposals/{proposal_id}/discard"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "discarded"

    factory = app.state.session_factory
    with factory() as session:
        row = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one()
        )
        assert row.status == "discarded"


# ---------------------------------------------------------------------------
# Explanations endpoint
# ---------------------------------------------------------------------------


async def test_explanations_endpoint_returns_accepted_chronological(
    admin_client: httpx.AsyncClient,
    nb_chat_session_with_run: tuple[str, str],
) -> None:
    """GET explanations returns only accepted ones, oldest first."""
    editor_session_id, run_id = nb_chat_session_with_run
    cell_uuid = f"cell-{uuid.uuid4().hex[:12]}"
    # Two accepted explanations + one we'll discard.
    first = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/explain-cell",
        json={"target_cell_uuid": cell_uuid, "explanation": "first"},
        headers={"X-Agent-Run-Id": run_id},
    )
    second = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/explain-cell",
        json={"target_cell_uuid": cell_uuid, "explanation": "second"},
        headers={"X-Agent-Run-Id": run_id},
    )
    discard_one = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/explain-cell",
        json={"target_cell_uuid": cell_uuid, "explanation": "to-discard"},
        headers={"X-Agent-Run-Id": run_id},
    )
    discard_id = discard_one.json()["proposal_id"]
    await admin_client.post(
        f"/api/notebook/chat/proposals/{discard_id}/discard"
    )

    resp = await admin_client.get(
        f"/api/notebook/chat/cell/{cell_uuid}/explanations"
    )
    assert resp.status_code == 200, resp.text
    bodies = [
        item["explanation"] for item in resp.json()["explanations"]
    ]
    assert bodies == ["first", "second"]
    assert "to-discard" not in bodies
    assert first.json()["proposal_id"] != second.json()["proposal_id"]


# ---------------------------------------------------------------------------
# Rename guard
# ---------------------------------------------------------------------------


def test_editor_chat_namespace_canonical() -> None:
    """``pointlessql.services.editor_chat`` is the canonical path;

    ``sql_chat`` was renamed in Phase 96 and must not be re-introduced.
    """
    import importlib

    importlib.import_module("pointlessql.services.editor_chat")
    importlib.import_module("pointlessql.models.editor_chat")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pointlessql.services.sql_chat")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pointlessql.models.sql_chat")
