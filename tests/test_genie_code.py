"""Tests for the Genie Code agentic-authoring command center."""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services import genie_code


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"genie-{uuid.uuid4().hex[:10]}",
            name="Genie Code test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_run(ws: int, *, status: str, harness: str | None = None) -> str:
    run_id = uuid.uuid4().hex
    with _factory()() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=ws,
                notebook_path="demo/run.py",
                status=status,
                harness=harness,
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return run_id


def test_authoring_surfaces_registry() -> None:
    surfaces = genie_code.authoring_surfaces()
    keys = {s["key"] for s in surfaces}
    assert keys == {"sql", "notebook", "pipeline", "ingest", "jobs", "runs", "ml"}
    for surface in surfaces:
        assert {"key", "label", "description", "href", "icon"} <= set(surface)
        assert surface["href"].startswith("/")


def test_overview_stats_and_recent() -> None:
    ws = _fresh_workspace()
    _seed_run(ws, status="succeeded")
    _seed_run(ws, status="failed")
    _seed_run(ws, status="needs_approval")
    _seed_run(ws, status="running", harness="langgraph")

    ov = genie_code.command_center_overview(_factory(), workspace_id=ws)

    assert ov["stats"]["total"] == 4
    assert ov["stats"]["succeeded"] == 1
    assert ov["stats"]["failed"] == 1
    assert ov["stats"]["needs_approval"] == 1
    assert ov["stats"]["active"] == 2  # running + needs_approval are non-terminal
    assert len(ov["recent_runs"]) == 4
    assert {s["key"] for s in ov["surfaces"]} >= {"sql", "runs", "ml"}


def test_overview_respects_limit() -> None:
    ws = _fresh_workspace()
    for _ in range(5):
        _seed_run(ws, status="succeeded")
    ov = genie_code.command_center_overview(_factory(), workspace_id=ws, limit=2)
    assert ov["stats"]["total"] == 5
    assert len(ov["recent_runs"]) == 2


@pytest.mark.asyncio
async def test_route_overview(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/genie-code/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"surfaces", "stats", "recent_runs"} <= set(data)
    assert len(data["surfaces"]) == 7


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/genie-code")
    assert resp.status_code == 200, resp.text
    assert "Genie Code" in resp.text
