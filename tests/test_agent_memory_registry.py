"""Route tests for the agent-memory registry.

Seeds ``AgentRun`` / ``AgentRunOperation`` rows directly through the live
app session factory (the registry is a pure read-rollup, so there is no
registration endpoint for the aggregate) and exercises the HTML page,
the JSON sibling, the substring filter, and the auth gate.
"""

from __future__ import annotations

import datetime
import json
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import AgentRun, AgentRunOperation


def _seed_agent(
    agent_id: str,
    *,
    runs: int = 1,
    ops_per_run: int = 0,
    status: str = "succeeded",
    workspace_id: int = 1,
) -> None:
    """Insert *runs* runs (each with *ops_per_run* ops) for one agent.

    Args:
        agent_id: Runtime agent identifier to attribute the runs to.
        runs: Number of ``AgentRun`` rows to create.
        ops_per_run: Number of ``AgentRunOperation`` rows per run.
        status: Status stamped on every seeded run.
        workspace_id: Workspace the rows belong to (1 = admin default).
    """
    factory = fastapi_app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        for _ in range(runs):
            run_id = str(uuid.uuid4())
            session.add(
                AgentRun(
                    id=run_id,
                    workspace_id=workspace_id,
                    principal="seed@test.com",
                    agent_id=agent_id,
                    notebook_path="registry_test.py",
                    status=status,
                    started_at=now,
                    finished_at=now,
                )
            )
            session.flush()
            for ordinal in range(1, ops_per_run + 1):
                session.add(
                    AgentRunOperation(
                        workspace_id=workspace_id,
                        agent_run_id=run_id,
                        ordinal=ordinal,
                        op_name="sql",
                        params_json=json.dumps({"query": "SELECT 1"}),
                        started_at=now,
                        finished_at=now,
                    )
                )
        session.commit()


@pytest.mark.asyncio
async def test_registry_page_renders(admin_client: httpx.AsyncClient) -> None:
    agent_id = f"reg-page-{uuid.uuid4().hex[:8]}"
    _seed_agent(agent_id)

    response = await admin_client.get("/agent-memories", params={"q": agent_id})
    assert response.status_code == 200, response.text
    assert "Agent Memories" in response.text
    assert agent_id in response.text


@pytest.mark.asyncio
async def test_registry_api_aggregates_counts(admin_client: httpx.AsyncClient) -> None:
    agent_id = f"reg-counts-{uuid.uuid4().hex[:8]}"
    _seed_agent(agent_id, runs=2, ops_per_run=3)

    response = await admin_client.get("/api/agent-memories", params={"q": agent_id})
    assert response.status_code == 200, response.text
    payload = response.json()

    rows = [a for a in payload["agents"] if a["agent_id"] == agent_id]
    assert len(rows) == 1
    row = rows[0]
    assert row["run_count"] == 2
    assert row["op_count"] == 6
    assert row["status_counts"] == {"succeeded": 2}
    assert row["principal"] == "seed@test.com"
    assert row["last_activity"] is not None


@pytest.mark.asyncio
async def test_registry_search_filters_by_agent_id(admin_client: httpx.AsyncClient) -> None:
    token = uuid.uuid4().hex[:6]
    keep = f"regalpha{token}"
    drop = f"regbeta{token}"
    _seed_agent(keep)
    _seed_agent(drop)

    response = await admin_client.get("/api/agent-memories", params={"q": f"regalpha{token}"})
    assert response.status_code == 200, response.text
    returned = {a["agent_id"] for a in response.json()["agents"]}
    assert keep in returned
    assert drop not in returned


@pytest.mark.asyncio
async def test_registry_requires_auth(anonymous_client: httpx.AsyncClient) -> None:
    response = await anonymous_client.get("/agent-memories", follow_redirects=False)
    assert response.status_code in {302, 303, 307, 401, 403}
