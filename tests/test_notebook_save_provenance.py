"""save-path provenance flush integration test.

When ``POST /api/notebooks/save`` carries ``proposal_acceptances``,
the route should write one ``NotebookCellProvenance`` row per
acceptance and stamp ``inserted_cell_uuid`` on the matching
:class:`NotebookCellProposal` — keyed on the cell_uuid the
reconciler minted for the new cell.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    EditorChatSession,
    NotebookCellProposal,
    NotebookCellProvenance,
)

_SEED = b"""\
# %%
x = 1
"""


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin notebooks dir to an isolated tmp path."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


@pytest.fixture
def seed_chat_session() -> tuple[str, str]:
    """Seed an EditorChatSession + AgentRun and tear down after the test."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    editor_session_id = f"nb-save-prov-{uuid.uuid4().hex[:8]}"
    with factory() as session:
        now = datetime.datetime.now(datetime.UTC)
        session.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id="nb-save-prov",
                notebook_path="/internal/save-prov",
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
        for prov in (
            session.query(NotebookCellProvenance)
            .filter(NotebookCellProvenance.agent_run_id == run_id)
            .all()
        ):
            session.delete(prov)
        for prop in (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.accepted_run_id == run_id)
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


async def test_save_flushes_propose_provenance(
    workspace_dir: Path,
    admin_client: httpx.AsyncClient,
    seed_chat_session: tuple[str, str],
) -> None:
    """A propose acceptance threaded via save writes a provenance row."""
    editor_session_id, run_id = seed_chat_session
    (workspace_dir / "demo.py").write_bytes(_SEED)

    # 1) Agent posts a propose-cell draft.
    propose_resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/propose-cell",
        json={
            "cell_type": "code",
            "source": "y = 2  # new cell from agent",
            "position_at_end": True,
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    assert propose_resp.status_code == 200
    proposal_id = propose_resp.json()["proposal_id"]

    # 2) User clicks Insert → accept route.
    accept_resp = await admin_client.post(f"/api/notebook/chat/proposals/{proposal_id}/accept")
    assert accept_resp.status_code == 200
    accept_body = accept_resp.json()

    # 3) Browser updates the in-memory cells array and saves; we
    #    simulate that by POSTing cells with the new cell appended
    #    plus a proposal_acceptances entry pointing at its index.
    save_resp = await admin_client.post(
        "/api/notebooks/save",
        json={
            "path": "demo.py",
            "cells": [
                {"cell_type": "code", "source": "x = 1"},
                {
                    "cell_type": accept_body["cell_type"],
                    "source": accept_body["new_source"],
                },
            ],
            "proposal_acceptances": [
                {
                    "proposal_id": proposal_id,
                    "agent_run_id": run_id,
                    "action": "propose",
                    "placeholder_index": 1,
                }
            ],
        },
    )
    assert save_resp.status_code == 200, save_resp.text
    new_cell_uuid = save_resp.json()["cells"][1]["cell_uuid"]
    assert new_cell_uuid

    # 4) Provenance row should exist and the proposal should now
    #    carry the final cell_uuid as its back-reference.
    factory = app.state.session_factory
    with factory() as session:
        prov_rows = (
            session.query(NotebookCellProvenance)
            .filter(NotebookCellProvenance.proposal_id == proposal_id)
            .all()
        )
        assert len(prov_rows) == 1
        assert prov_rows[0].cell_uuid == new_cell_uuid
        assert prov_rows[0].action == "propose"
        assert prov_rows[0].agent_run_id == run_id
        prop = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one()
        )
        assert prop.inserted_cell_uuid == new_cell_uuid


async def test_save_flushes_fix_provenance(
    workspace_dir: Path,
    admin_client: httpx.AsyncClient,
    seed_chat_session: tuple[str, str],
) -> None:
    """A fix acceptance writes a provenance row keyed on target_cell_uuid."""
    editor_session_id, run_id = seed_chat_session
    (workspace_dir / "demo.py").write_bytes(_SEED)

    # First save establishes a real cell_uuid the fix can target.
    initial = await admin_client.post(
        "/api/notebooks/save",
        json={
            "path": "demo.py",
            "cells": [{"cell_type": "code", "source": "x = 1"}],
        },
    )
    assert initial.status_code == 200
    target_uuid = initial.json()["cells"][0]["cell_uuid"]

    # Agent posts a fix; user accepts.
    fix_resp = await admin_client.post(
        f"/api/notebook/chat/{editor_session_id}/fix-cell",
        json={
            "target_cell_uuid": target_uuid,
            "new_source": "x = 99  # fixed",
        },
        headers={"X-Agent-Run-Id": run_id},
    )
    proposal_id = fix_resp.json()["proposal_id"]
    accept = await admin_client.post(f"/api/notebook/chat/proposals/{proposal_id}/accept")
    assert accept.status_code == 200

    # Save with the patched source + a fix acceptance.
    save_resp = await admin_client.post(
        "/api/notebooks/save",
        json={
            "path": "demo.py",
            "cells": [{"cell_type": "code", "source": "x = 99  # fixed"}],
            "proposal_acceptances": [
                {
                    "proposal_id": proposal_id,
                    "agent_run_id": run_id,
                    "action": "fix",
                    "target_cell_uuid": target_uuid,
                }
            ],
        },
    )
    assert save_resp.status_code == 200

    factory = app.state.session_factory
    with factory() as session:
        prov = (
            session.query(NotebookCellProvenance)
            .filter(NotebookCellProvenance.proposal_id == proposal_id)
            .one()
        )
        assert prov.action == "fix"
        assert prov.cell_uuid == target_uuid
