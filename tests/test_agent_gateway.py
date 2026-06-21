"""Tests for the agent-gateway governance overlay.

The service-level tests each run in a freshly-created workspace so the
session-scoped test DB (no per-test rollback) cannot leak runs between
cases; the route tests hit the admin endpoints in the default workspace
and assert shape + auth, plus the harness round-trip through ingestion.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services import agent_gateway


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    """Create an isolated workspace and return its id."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"gw-{uuid.uuid4().hex[:10]}",
            name="Agent gateway test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_run(
    ws: int,
    *,
    harness: str | None = None,
    principal: str | None = None,
    cost: float | None = None,
    status: str = "succeeded",
    started_at: datetime.datetime | None = None,
) -> str:
    """Insert one synthetic agent run and return its id."""
    run_id = uuid.uuid4().hex
    with _factory()() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=ws,
                principal=principal,
                notebook_path="demo/run.py",
                status=status,
                cost_est=Decimal(str(cost)) if cost is not None else None,
                harness=harness,
                started_at=started_at or datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return run_id


def test_overview_rolls_up_by_harness_and_principal() -> None:
    ws = _fresh_workspace()
    _seed_run(ws, harness="langgraph", principal="a@x", cost=2, status="succeeded")
    _seed_run(ws, harness="langgraph", principal="b@x", cost=3, status="failed")
    _seed_run(ws, harness="crewai", principal="a@x", cost=6, status="running")

    ov = agent_gateway.gateway_overview(_factory(), workspace_id=ws)

    assert ov["totals"]["run_count"] == 3
    assert ov["totals"]["total_cost"] == 11.0
    assert ov["totals"]["distinct_harnesses"] == 2
    assert ov["totals"]["distinct_principals"] == 2
    assert ov["totals"]["active"] == 1

    by_h = {row["key"]: row for row in ov["by_harness"]}
    assert by_h["langgraph"]["run_count"] == 2
    assert by_h["langgraph"]["total_cost"] == 5.0
    assert by_h["langgraph"]["avg_cost"] == 2.5
    assert by_h["langgraph"]["failed"] == 1
    assert by_h["langgraph"]["distinct_principals"] == 2
    assert by_h["crewai"]["active"] == 1
    # Sorted by spend descending: crewai (6) outranks langgraph (5).
    assert ov["by_harness"][0]["key"] == "crewai"


def test_overview_unspecified_harness_and_principal() -> None:
    ws = _fresh_workspace()
    _seed_run(ws, harness=None, principal=None, cost=1, status="queued")

    ov = agent_gateway.gateway_overview(_factory(), workspace_id=ws)

    assert {row["key"] for row in ov["by_harness"]} == {agent_gateway.UNSPECIFIED_HARNESS}
    assert {row["key"] for row in ov["by_principal"]} == {agent_gateway.UNSPECIFIED_PRINCIPAL}


def test_overview_distinct_counts_use_normalized_members() -> None:
    # A run with a missing principal still contributes the normalized
    # UNSPECIFIED principal to its harness bucket's distinct count, so
    # the per-bucket figure agrees with the top-level distinct total
    # instead of silently dropping the unspecified run.
    ws = _fresh_workspace()
    _seed_run(ws, harness="langgraph", principal=None, cost=1)
    _seed_run(ws, harness="langgraph", principal="real@x", cost=1)

    ov = agent_gateway.gateway_overview(_factory(), workspace_id=ws)

    by_h = {row["key"]: row for row in ov["by_harness"]}
    assert by_h["langgraph"]["distinct_principals"] == 2
    assert ov["totals"]["distinct_principals"] == 2


def test_overview_budget_thresholds() -> None:
    ws = _fresh_workspace()
    _seed_run(ws, harness="x", cost=90, status="succeeded")

    ok = agent_gateway.gateway_overview(_factory(), workspace_id=ws, budget=Decimal("200"))
    assert ok["budget"]["status"] == "ok"

    warn = agent_gateway.gateway_overview(_factory(), workspace_id=ws, budget=Decimal("100"))
    assert warn["budget"]["status"] == "warn"
    assert warn["budget"]["signal_kind"] == "budget_warn"

    exhausted = agent_gateway.gateway_overview(_factory(), workspace_id=ws, budget=Decimal("50"))
    assert exhausted["budget"]["status"] == "exhausted"
    assert exhausted["budget"]["signal_kind"] == "budget_block"
    assert exhausted["budget"]["amount"] == 50.0
    assert exhausted["budget"]["accrued"] == 90.0

    assert agent_gateway.gateway_overview(_factory(), workspace_id=ws)["budget"] is None


def test_overview_since_filter() -> None:
    ws = _fresh_workspace()
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
    recent = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    _seed_run(ws, harness="old", cost=1, started_at=old)
    _seed_run(ws, harness="new", cost=2, started_at=recent)

    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    ov = agent_gateway.gateway_overview(_factory(), workspace_id=ws, since=cutoff)

    assert {row["key"] for row in ov["by_harness"]} == {"new"}
    assert ov["totals"]["run_count"] == 1


def test_overview_recent_runs_newest_first() -> None:
    ws = _fresh_workspace()
    t1 = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=3)
    t2 = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    _seed_run(ws, harness="h1", started_at=t1)
    newest = _seed_run(ws, harness="h2", started_at=t2)

    ov = agent_gateway.gateway_overview(_factory(), workspace_id=ws)

    assert ov["recent_runs"][0]["id"] == newest
    assert ov["recent_runs"][0]["harness"] == "h2"


@pytest.mark.asyncio
async def test_ingestion_roundtrips_harness(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/agent-runs",
        json={
            "notebook_path": "demo/run.py",
            "source": "print('hi')\n",
            "runtime_versions": {"python": "3.14"},
            "harness": "claude-code-sdk",
            "cost_est": "1.50",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["harness"] == "claude-code-sdk"


@pytest.mark.asyncio
async def test_route_overview(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/admin/agent-gateway/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"totals", "by_harness", "by_principal", "recent_runs", "budget"} <= set(data)
    assert data["budget"] is None

    with_budget = await admin_client.get("/api/admin/agent-gateway/overview?budget=1000000")
    assert with_budget.json()["budget"]["status"] == "ok"


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/admin/agent-gateway")
    assert resp.status_code == 200, resp.text
    assert "Agent gateway" in resp.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/admin/agent-gateway/overview")
    assert resp.status_code in {401, 403}
