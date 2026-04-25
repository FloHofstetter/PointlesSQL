"""Tests for the Sprint 13.11.1 ``GET /api/agent-runs/{id}/full`` route.

Backs the ``pql_my_run`` Hermes tool — joins the run row with every
per-run sibling table the supervision view aggregates.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


async def _seed_run(client: httpx.AsyncClient, run_id: str) -> None:
    response = await client.post(
        "/api/agent-runs",
        json={
            "id": run_id,
            "notebook_path": "demo/full.py",
            "source": "print('seed')\n",
            "runtime_versions": {"python": "3.14.0"},
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_full_returns_run_and_collections_for_fresh_run() -> None:
    run_id = "f1111111-1111-1111-1111-111111111111"
    async with _admin_client() as client:
        await _seed_run(client, run_id)
        response = await client.get(f"/api/agent-runs/{run_id}/full")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run"]["id"] == run_id
    assert payload["run"]["notebook_path"] == "demo/full.py"
    # Source persisted by the strict POST contract.
    assert payload["source"] is not None
    assert payload["source"]["source_bytes"] == "print('seed')\n"
    # Fresh run has no operations / tool calls / queries yet, but
    # the lifecycle "started" event was emitted by Sprint 13.3.
    assert payload["operations"] == []
    assert payload["tool_calls"] == []
    assert payload["queries"] == []
    assert isinstance(payload["events"], list)


@pytest.mark.asyncio
async def test_full_returns_404_for_unknown_run() -> None:
    async with _admin_client() as client:
        response = await client.get(
            "/api/agent-runs/deadbeef-dead-beef-dead-beefdeadbeef/full"
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_includes_tool_calls_after_record() -> None:
    run_id = "f2222222-2222-2222-2222-222222222222"
    async with _admin_client() as client:
        await _seed_run(client, run_id)
        record = await client.post(
            f"/api/agent-runs/{run_id}/tool-call",
            json={
                "tool_name": "pql_query",
                "args_json": '{"sql": "SELECT 1"}',
                "duration_ms": 4,
            },
        )
        assert record.status_code == 200, record.text
        response = await client.get(f"/api/agent-runs/{run_id}/full")
    assert response.status_code == 200
    payload = response.json()
    tool_calls = payload["tool_calls"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool_name"] == "pql_query"
    assert "SELECT 1" in tool_calls[0]["args_json"]
