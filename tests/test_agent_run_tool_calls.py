"""Tests for the Sprint 13.7.4 ``POST /api/agent-runs/{id}/tool-call`` route.

Persists one ``agent_run_tool_calls`` row + emits a
``pointlessql.agent_run.tool_call`` CloudEvent. Covers the strict
input validation, FK lookup, and the audit + event side-effects.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunEvent, AgentRunToolCall



async def _seed_run(client: httpx.AsyncClient, run_id: str) -> None:
    """POST a strict agent_runs row so subsequent tool-call POSTs succeed."""
    response = await client.post(
        "/api/agent-runs",
        json={
            "id": run_id,
            "notebook_path": "demo/run.py",
            "source": "print('seed')\n",
            "runtime_versions": {"python": "3.14.0"},
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_tool_call_persists_row_and_emits_event(admin_client: httpx.AsyncClient) -> None:
    run_id = "aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"
    await _seed_run(admin_client, run_id)
    response = await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={
            "tool_name": "pql_query",
            "args_json": '{"sql": "SELECT 1"}',
            "result_summary": '{"ok": true, "rows": [[1]]}',
            "duration_ms": 7,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == run_id  # CloudEvent-source key
    assert payload["tool_call_id"] >= 1
    assert payload["tool_name"] == "pql_query"
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(select(AgentRunToolCall).where(AgentRunToolCall.agent_run_id == run_id))
            .scalars()
            .all()
        )
        events = (
            session.execute(
                select(AgentRunEvent).where(
                    AgentRunEvent.agent_run_id == run_id,
                    AgentRunEvent.event_type == "pointlessql.agent_run.tool_call",
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    row = rows[0]
    assert row.tool_name == "pql_query"
    assert "SELECT 1" in row.args_json
    assert "rows" in (row.result_summary or "")
    assert row.duration_ms == 7
    assert isinstance(row.called_at, datetime)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_tool_call_rejects_missing_tool_name(admin_client: httpx.AsyncClient) -> None:
    run_id = "bbbbbbbb-1111-1111-1111-bbbbbbbbbbbb"
    await _seed_run(admin_client, run_id)
    response = await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={"args_json": "{}"},
    )
    assert response.status_code == 422
    assert "tool_name" in response.text.lower()


@pytest.mark.asyncio
async def test_tool_call_404_for_unknown_run(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.post(
        "/api/agent-runs/no-such-run/tool-call",
        json={"tool_name": "pql_query"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tool_call_accepts_dict_args_json(admin_client: httpx.AsyncClient) -> None:
    """Plugin sends ``args_json`` as a dict; route serialises it."""
    run_id = "cccccccc-1111-1111-1111-cccccccccccc"
    await _seed_run(admin_client, run_id)
    response = await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={
            "tool_name": "pql_get_table",
            "args_json": {"full_name": "main.gold.orders"},
        },
    )
    assert response.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(AgentRunToolCall).where(AgentRunToolCall.agent_run_id == run_id)
        ).scalar_one()
    # Dict input gets sorted-JSON-serialised so the trail is
    # diff-friendly across runs.
    assert "main.gold.orders" in row.args_json


@pytest.mark.asyncio
async def test_tool_call_clamps_called_at_to_iso(admin_client: httpx.AsyncClient) -> None:
    run_id = "dddddddd-1111-1111-1111-dddddddddddd"
    fixed = datetime(2026, 4, 25, 12, 30, tzinfo=UTC)
    await _seed_run(admin_client, run_id)
    response = await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={
            "tool_name": "pql_query",
            "called_at": fixed.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(AgentRunToolCall).where(AgentRunToolCall.agent_run_id == run_id)
        ).scalar_one()
    # SQLite drops tzinfo on read; compare wall-clock components.
    assert row.called_at.replace(tzinfo=UTC) == fixed


@pytest.mark.asyncio
async def test_tool_call_truncates_oversized_result_summary(admin_client: httpx.AsyncClient) -> None:
    run_id = "eeeeeeee-1111-1111-1111-eeeeeeeeeeee"
    huge = "x" * 5000
    await _seed_run(admin_client, run_id)
    response = await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={"tool_name": "pql_query", "result_summary": huge},
    )
    assert response.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(AgentRunToolCall).where(AgentRunToolCall.agent_run_id == run_id)
        ).scalar_one()
    assert row.result_summary is not None
    assert len(row.result_summary) <= 2000


@pytest.mark.asyncio
async def test_run_seed_unaffected_by_tool_call_inserts(admin_client: httpx.AsyncClient) -> None:
    """A successful tool-call POST does not flip the parent run state."""
    run_id = "ffffffff-1111-1111-1111-ffffffffffff"
    await _seed_run(admin_client, run_id)
    await admin_client.post(
        f"/api/agent-runs/{run_id}/tool-call",
        json={"tool_name": "pql_query"},
    )
    factory = app.state.session_factory
    with factory() as session:
        run = session.execute(select(AgentRun).where(AgentRun.id == run_id)).scalar_one()
    assert run.status == "queued"
    assert run.finished_at is None
    # SHA still matches the seed source — sanity check that
    # the run row didn't get rewritten by the tool-call branch.
    assert run.source_snapshot_sha == hashlib.sha256(b"print('seed')\n").hexdigest()
