"""integration tests for the memory HTML + JSON routes.

Hits the FastAPI app via the shared ``admin_client`` /
``anonymous_client`` fixtures.  The branch + replay routes
monkeypatch the underlying ``pql.memory.*`` facades because the
real soyuz + deltalake plumbing belongs to the e2e walkthrough,
not the unit gate.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import AgentRun, AgentRunOperation


@pytest.fixture
def _seed_agent_with_ops() -> tuple[str, str]:
    """Insert one AgentRun + one write op into the live app DB.

    Returns:
        ``(agent_id, run_id)`` pair.
    """
    factory = fastapi_app.state.session_factory
    agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="memory_route_test.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="write_table",
                params_json=json.dumps({"full_name": "main.bronze.orders"}),
                target_table="main.bronze.orders",
                delta_version_before=3,
                started_at=now,
                finished_at=now,
            )
        )
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=2,
                op_name="sql",
                params_json=json.dumps({"query": "SELECT * FROM main.bronze.orders"}),
                target_table=None,
                started_at=now,
                finished_at=now,
            )
        )
        s.commit()
    return agent_id, run_id


class TestMemoryPage:
    """GET /memory/{agent_id} happy + error paths."""

    async def test_anonymous_redirects_to_login(
        self,
        anonymous_client: httpx.AsyncClient,
    ) -> None:
        response = await anonymous_client.get("/memory/some-agent")
        assert response.status_code in (303, 307)
        assert "/auth/login" in response.headers["location"]

    async def test_admin_can_view_memory_page(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
    ) -> None:
        agent_id, _ = _seed_agent_with_ops
        response = await admin_client.get(f"/memory/{agent_id}")
        assert response.status_code == 200
        body = response.text
        assert agent_id in body

    async def test_unknown_agent_renders_empty_state(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        response = await admin_client.get("/memory/never-seen-this-one")
        # No 404 — empty memory is a valid state for unknown agent_ids.
        assert response.status_code == 200


class TestRecallEndpoint:
    """GET /api/memory/{agent_id}/recall."""

    async def test_recall_returns_operations(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
    ) -> None:
        agent_id, _ = _seed_agent_with_ops
        response = await admin_client.get(f"/api/memory/{agent_id}/recall")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert data["count"] >= 2
        op_names = {op["op_name"] for op in data["operations"]}
        assert "write_table" in op_names
        assert "sql" in op_names

    async def test_recall_filters_by_op_name(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
    ) -> None:
        agent_id, _ = _seed_agent_with_ops
        response = await admin_client.get(
            f"/api/memory/{agent_id}/recall",
            params={"op_name": "sql"},
        )
        assert response.status_code == 200
        ops = response.json()["operations"]
        assert all(op["op_name"] == "sql" for op in ops)

    async def test_recall_rejects_unknown_op_name(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        response = await admin_client.get(
            "/api/memory/some-agent/recall",
            params={"op_name": "bogus_op"},
        )
        assert response.status_code == 400

    async def test_recall_rejects_bad_since(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        response = await admin_client.get(
            "/api/memory/some-agent/recall",
            params={"since": "not-a-date"},
        )
        assert response.status_code == 400

    async def test_recall_anonymous_rejected(
        self,
        anonymous_client: httpx.AsyncClient,
    ) -> None:
        response = await anonymous_client.get("/api/memory/x/recall")
        assert response.status_code in (401, 403)


class TestBranchEndpoint:
    """POST /api/memory/{agent_id}/branch — monkeypatches the facade."""

    async def test_branch_calls_memory_branch_facade(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pointlessql.api.memory_routes import _branch as branch_route

        agent_id, run_id = _seed_agent_with_ops
        captured: dict[str, object] = {}

        def fake_branch(**kw: object) -> dict[str, object]:
            captured.update(kw)
            return {
                "branch_schema_fqn": "main.mem_x",
                "parent_schema_fqn": "main.bronze",
                "pinned_delta_version": 3,
                "intent": "create",
            }

        monkeypatch.setattr(branch_route.memory, "branch", fake_branch)

        response = await admin_client.post(
            f"/api/memory/{agent_id}/branch",
            json={
                "from_run_id": run_id,
                "pin_to_version": True,
                "intent": "create",
            },
        )
        assert response.status_code == 200
        assert response.json()["branch_schema_fqn"] == "main.mem_x"
        assert captured["agent_id"] == agent_id
        assert str(captured["from_run_id"]) == run_id

    async def test_branch_with_fork_intent_calls_fork(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pointlessql.api.memory_routes import _branch as branch_route

        agent_id, run_id = _seed_agent_with_ops
        calls: list[str] = []

        def fake_branch(**_: object) -> dict[str, object]:
            calls.append("branch")
            return {"intent": "create"}

        def fake_fork(**_: object) -> dict[str, object]:
            calls.append("fork")
            return {
                "branch_schema_fqn": "main.mem_x",
                "parent_schema_fqn": "main.bronze",
                "pinned_delta_version": 3,
                "intent": "fork",
            }

        monkeypatch.setattr(branch_route.memory, "branch", fake_branch)
        monkeypatch.setattr(branch_route.memory, "fork", fake_fork)

        response = await admin_client.post(
            f"/api/memory/{agent_id}/branch",
            json={"from_run_id": run_id, "intent": "fork"},
        )
        assert response.status_code == 200
        assert calls == ["fork"]
        assert response.json()["intent"] == "fork"


class TestReplayEndpoint:
    """POST /api/memory/{agent_id}/replay."""

    async def test_replay_returns_skip_summary_with_hx_redirect(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pointlessql.api.memory_routes import _replay as replay_route
        from pointlessql.services.agent_runs.memory._replay_policy import (
            ReplayResult,
            ReplaySkip,
        )
        from pointlessql.types import OpId, OpName, RunId

        agent_id, run_id = _seed_agent_with_ops
        new_run = RunId(str(uuid.uuid4()))

        def fake_replay(**_: object) -> ReplayResult:
            now = datetime.datetime.now(datetime.UTC)
            return ReplayResult(
                replay_run_id=new_run,
                ops_replayed=1,
                ops_skipped=(
                    ReplaySkip(
                        op_id=OpId(7),
                        op_name=OpName.MERGE,
                        reason="data_unavailable",
                    ),
                ),
                started_at=now,
                finished_at=now,
            )

        monkeypatch.setattr(replay_route.memory, "replay", fake_replay)

        response = await admin_client.post(
            f"/api/memory/{agent_id}/replay",
            json={
                "branch_schema_fqn": "main.mem_x",
                "source_run_id": run_id,
                "policy": "skip_unsafe",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == f"/runs/{new_run}"
        data = response.json()
        assert data["ops_replayed"] == 1
        assert len(data["ops_skipped"]) == 1
        assert data["ops_skipped"][0]["reason"] == "data_unavailable"

    async def test_replay_rejects_unknown_policy(
        self,
        admin_client: httpx.AsyncClient,
    ) -> None:
        response = await admin_client.post(
            "/api/memory/x/replay",
            json={
                "branch_schema_fqn": "main.x",
                "source_run_id": "00000000-0000-0000-0000-000000000000",
                "policy": "bogus_policy",
            },
        )
        assert response.status_code == 400

    async def test_replay_unsafe_under_strict_returns_422(
        self,
        admin_client: httpx.AsyncClient,
        _seed_agent_with_ops: tuple[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pointlessql.api.memory_routes import _replay as replay_route
        from pointlessql.services.agent_runs.memory._replay import ReplayUnsafeOpError

        agent_id, run_id = _seed_agent_with_ops

        def fake_replay(**_: object) -> Any:
            raise ReplayUnsafeOpError("op 7 (dbt_model) is unsafe")

        monkeypatch.setattr(replay_route.memory, "replay", fake_replay)

        response = await admin_client.post(
            f"/api/memory/{agent_id}/replay",
            json={
                "branch_schema_fqn": "main.mem_x",
                "source_run_id": run_id,
                "policy": "strict",
            },
        )
        assert response.status_code == 422
