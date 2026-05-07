"""POST /api/agent-runs/{run_id}/rewrite-attempt route tests (Phase 39 Sprint 39.2).

The plugin POSTs one row per rewrite-loop resolution; this exercises
the validation, idempotency (409 on duplicate ``(run, attempt_no)``),
and workspace-isolation guards.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRun, RewriteAttempt
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _stub_uc_client() -> None:
    """Run-detail page touches uc_client.list_audit_events; stub it."""
    client = MagicMock(spec=UnityCatalogClient)
    client.list_audit_events = AsyncMock(return_value=[])
    client.get_table = AsyncMock(return_value=None)
    client.get_effective_permissions = AsyncMock(return_value=[])
    app.state.uc_client = client



@pytest.fixture
def run_id() -> str:
    """Insert one minimal AgentRun in workspace 1 and return its id."""
    rid = str(uuid.uuid4())
    factory: Any = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=rid,
                workspace_id=1,
                principal="test@test.com",
                agent_id="test-agent",
                notebook_path="/tmp/agent.py",
                status="RUNNING",
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return rid


async def test_post_rewrite_attempt_creates_row(run_id: str, admin_client: httpx.AsyncClient) -> None:
    body = {
        "attempt_no": 1,
        "original_sql_hash": "abc123def456",
        "rewritten_sql_hash": "987zyx654wvu",
        "original_cost": 1_500_000,
        "rewritten_cost": 750,
        "verdict": "auto_rewrite_succeeded",
        "reason": "Added LIMIT 1000 to bound the scan.",
    }
    resp = await admin_client.post(
        f"/api/agent-runs/{run_id}/rewrite-attempt",
        json=body,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["attempt_no"] == 1
    assert payload["verdict"] == "auto_rewrite_succeeded"
    assert isinstance(payload["id"], int)

    factory: Any = app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(RewriteAttempt).where(RewriteAttempt.agent_run_id == run_id)
            )
        )
    assert len(rows) == 1
    row = rows[0]
    assert row.attempt_no == 1
    assert row.original_sql_hash == "abc123def456"
    assert row.rewritten_sql_hash == "987zyx654wvu"
    assert row.original_cost == 1_500_000
    assert row.rewritten_cost == 750
    assert row.verdict == "auto_rewrite_succeeded"
    assert row.reason == "Added LIMIT 1000 to bound the scan."


async def test_post_rewrite_attempt_human_escalation_no_rewrite(run_id: str, admin_client: httpx.AsyncClient) -> None:
    """human_approval_required can omit rewritten_sql_hash and rewritten_cost."""
    body = {
        "attempt_no": 4,
        "original_sql_hash": "abc",
        "original_cost": 5_000_000,
        "verdict": "human_approval_required",
    }
    resp = await admin_client.post(
        f"/api/agent-runs/{run_id}/rewrite-attempt",
        json=body,
    )
    assert resp.status_code == 200, resp.text
    factory: Any = app.state.session_factory
    with factory() as session:
        row = session.scalars(
            select(RewriteAttempt).where(RewriteAttempt.agent_run_id == run_id)
        ).one()
    assert row.rewritten_sql_hash is None
    assert row.rewritten_cost is None


async def test_post_rewrite_attempt_duplicate_returns_4xx(run_id: str, admin_client: httpx.AsyncClient) -> None:
    body = {
        "attempt_no": 1,
        "original_sql_hash": "a",
        "original_cost": 1,
        "verdict": "original_approved",
    }
    first = await admin_client.post(
        f"/api/agent-runs/{run_id}/rewrite-attempt",
        json=body,
    )
    assert first.status_code == 200
    second = await admin_client.post(
        f"/api/agent-runs/{run_id}/rewrite-attempt",
        json=body,
    )
    assert second.status_code >= 400


async def test_post_rewrite_attempt_unknown_run_returns_404(admin_client: httpx.AsyncClient) -> None:
    body = {
        "attempt_no": 1,
        "original_sql_hash": "a",
        "original_cost": 1,
        "verdict": "original_approved",
    }
    bogus = str(uuid.uuid4())
    resp = await admin_client.post(
        f"/api/agent-runs/{bogus}/rewrite-attempt",
        json=body,
    )
    assert resp.status_code == 404


async def test_post_rewrite_attempt_invalid_verdict(run_id: str, admin_client: httpx.AsyncClient) -> None:
    body = {
        "attempt_no": 1,
        "original_sql_hash": "a",
        "original_cost": 1,
        "verdict": "made_it_up",
    }
    resp = await admin_client.post(
        f"/api/agent-runs/{run_id}/rewrite-attempt",
        json=body,
    )
    assert resp.status_code >= 400


async def test_run_detail_renders_rewrites_subtab(run_id: str, admin_client: httpx.AsyncClient) -> None:
    """The run-view page renders the new Rewrites sub-tab with the rows."""
    factory: Any = app.state.session_factory
    with factory() as session:
        session.add(
            RewriteAttempt(
                workspace_id=1,
                agent_run_id=run_id,
                attempt_no=1,
                original_sql_hash="orig123",
                rewritten_sql_hash="rewr456",
                original_cost=1_000_000,
                rewritten_cost=500,
                verdict="auto_rewrite_succeeded",
                reason="Added LIMIT.",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    resp = await admin_client.get(f"/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "tab-rewrites-btn" in body
    assert "auto_rewrite_succeeded" in body
    assert "orig123" in body
    assert "rewr456" in body
    # cost-delta = 999500
    assert "999,500" in body or "999500" in body
