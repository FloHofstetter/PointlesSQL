"""Approvals lane — live-union of pending runs + terminal fan-out.

Agent runs in ``needs_approval`` are read straight from the source
table into the admin feed (never stored as notifications), so the
inline Approve / Deny card always reflects current state.  Resolving
the run drops the card and fans an informational ``approved`` /
``denied`` notice out to the run principal.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models.agent._runs import AgentRun


def _seed_pending_run(principal: str = "nonadmin@test.com") -> str:
    run_id = str(uuid.uuid4())
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=1,
                principal=principal,
                agent_id="etl",
                notebook_path="pipelines/sales.py",
                status="needs_approval",
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return run_id


@pytest.mark.asyncio
async def test_pending_run_appears_as_approval_card_for_admin(
    admin_client: httpx.AsyncClient,
) -> None:
    run_id = _seed_pending_run()
    r = await admin_client.get("/api/feed")
    assert r.status_code == 200
    body = r.json()
    approvals = [row for row in body["rows"] if row.get("render_kind") == "approval"]
    assert len(approvals) == 1
    card = approvals[0]
    assert card["run_id"] == run_id
    assert card["category"] == "approval"
    assert card["entity_kind"] == "run"
    assert card["entity_ref"] == run_id
    assert body["category_counts"].get("approval") == 1


@pytest.mark.asyncio
async def test_pending_run_hidden_from_non_admin(
    non_admin_client: httpx.AsyncClient,
) -> None:
    _seed_pending_run()
    r = await non_admin_client.get("/api/feed")
    assert r.status_code == 200
    approvals = [row for row in r.json()["rows"] if row.get("render_kind") == "approval"]
    assert approvals == []


@pytest.mark.asyncio
async def test_category_slice_returns_only_approvals(
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_pending_run()
    r = await admin_client.get("/api/feed?category=approval")
    rows = r.json()["rows"]
    assert rows, "expected the pending run under the approval lane"
    assert all(row["category"] == "approval" for row in rows)


@pytest.mark.asyncio
async def test_approving_removes_card_and_notifies_principal(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    run_id = _seed_pending_run(principal="nonadmin@test.com")

    # Admin approves.
    approve = await admin_client.post(f"/api/agent-runs/{run_id}/approve")
    assert approve.status_code == 200

    # The live approval card is gone from the admin feed.
    r = await admin_client.get("/api/feed")
    approvals = [row for row in r.json()["rows"] if row.get("render_kind") == "approval"]
    assert approvals == []

    # The principal (non-admin) received an informational approved notice.
    r = await non_admin_client.get("/api/feed")
    approved = [
        row for row in r.json()["rows"] if row.get("event_type") == "pointlessql.agent_run.approved"
    ]
    assert len(approved) == 1
    assert approved[0]["category"] == "approval"


@pytest.mark.asyncio
async def test_denying_notifies_principal_with_reason(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    run_id = _seed_pending_run(principal="nonadmin@test.com")

    deny = await admin_client.post(
        f"/api/agent-runs/{run_id}/deny",
        json={"reason": "cost gate"},
    )
    assert deny.status_code == 200

    r = await non_admin_client.get("/api/feed")
    denied = [
        row for row in r.json()["rows"] if row.get("event_type") == "pointlessql.agent_run.denied"
    ]
    assert len(denied) == 1
    assert "cost gate" in denied[0]["summary_md"]
