"""Tests for the Sprint 13.8 forced-audit-trail surface."""

from __future__ import annotations

import datetime
import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models import (
    AgentRun,
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
)
from pointlessql.services.agent_runs import (
    EVENT_TYPE_STARTED,
    emit_agent_run_event,
    operation_context,
    record_operation,
)


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


# ---------------------------------------------------------------------------
# POST /api/agent-runs strict mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_agent_run_requires_source() -> None:
    async with _admin_client() as client:
        response = await client.post(
            "/api/agent-runs",
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "notebook_path": "demo/run.py",
                "runtime_versions": {"python": "3.14.0"},
            },
        )
    assert response.status_code == 422
    assert "source" in response.text.lower()


@pytest.mark.asyncio
async def test_post_agent_run_requires_runtime_versions() -> None:
    async with _admin_client() as client:
        response = await client.post(
            "/api/agent-runs",
            json={
                "id": "22222222-2222-2222-2222-222222222222",
                "notebook_path": "demo/run.py",
                "source": "print('hi')\n",
            },
        )
    assert response.status_code == 422
    assert "runtime_versions" in response.text.lower()


@pytest.mark.asyncio
async def test_post_agent_run_persists_source() -> None:
    source = "import pql\npql.PQL().table('main.bronze.foo')\n"
    expected_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    run_id = "33333333-3333-3333-3333-333333333333"
    async with _admin_client() as client:
        response = await client.post(
            "/api/agent-runs",
            json={
                "id": run_id,
                "notebook_path": "demo/run.py",
                "source": source,
                "runtime_versions": {"python": "3.14.0", "deltalake": "1.5.0"},
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == run_id
    assert body["source_snapshot_sha"] == expected_sha
    assert body["runtime_versions"] == {"python": "3.14.0", "deltalake": "1.5.0"}

    factory = app.state.session_factory
    with factory() as session:
        source_row = session.scalar(
            select(AgentRunSource).where(AgentRunSource.agent_run_id == run_id)
        )
        assert source_row is not None
        assert source_row.source_bytes == source
        assert source_row.source_sha == expected_sha


@pytest.mark.asyncio
async def test_post_agent_run_rejects_sha_mismatch() -> None:
    async with _admin_client() as client:
        response = await client.post(
            "/api/agent-runs",
            json={
                "id": "44444444-4444-4444-4444-444444444444",
                "notebook_path": "demo/run.py",
                "source": "print('hi')\n",
                "source_snapshot_sha": "0" * 64,
                "runtime_versions": {"python": "3.14.0"},
            },
        )
    assert response.status_code == 422
    assert "source_snapshot_sha mismatch" in response.text


# ---------------------------------------------------------------------------
# operations service
# ---------------------------------------------------------------------------


def _create_run(run_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") -> str:
    """Insert an AgentRun fixture and return its id."""
    factory = app.state.session_factory
    with factory() as session:
        row = AgentRun(
            id=run_id,
            principal=None,
            agent_id="test-agent",
            notebook_path="demo/x.py",
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(row)
        session.commit()
    return run_id


def test_record_operation_inserts_and_assigns_ordinal() -> None:
    run_id = _create_run("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    factory = app.state.session_factory
    started = datetime.datetime.now(datetime.UTC)
    finished = started + datetime.timedelta(milliseconds=10)

    record_operation(
        factory,
        agent_run_id=run_id,
        op_name="write_table",
        params={"full_name": "main.bronze.foo", "mode": "overwrite"},
        target_table="main.bronze.foo",
        input_sha="a" * 64,
        rows_affected=42,
        delta_version_before=None,
        delta_version_after=0,
        started_at=started,
        finished_at=finished,
        error_message=None,
    )
    record_operation(
        factory,
        agent_run_id=run_id,
        op_name="sql",
        params={"query": "SELECT 1"},
        target_table=None,
        input_sha=None,
        rows_affected=1,
        delta_version_before=None,
        delta_version_after=None,
        started_at=started,
        finished_at=finished,
        error_message=None,
    )
    with factory() as session:
        rows = session.scalars(
            select(AgentRunOperation)
            .where(AgentRunOperation.agent_run_id == run_id)
            .order_by(AgentRunOperation.ordinal)
        ).all()
    assert [r.ordinal for r in rows] == [1, 2]
    assert rows[0].op_name == "write_table"
    assert rows[1].op_name == "sql"


def test_record_operation_unknown_run_raises() -> None:
    with pytest.raises(AuditUnavailableError):
        record_operation(
            app.state.session_factory,
            agent_run_id="does-not-exist",
            op_name="sql",
            params={"query": "SELECT 1"},
            target_table=None,
            input_sha=None,
            rows_affected=None,
            delta_version_before=None,
            delta_version_after=None,
            started_at=datetime.datetime.now(datetime.UTC),
            finished_at=None,
            error_message=None,
        )


def test_operation_context_records_failure() -> None:
    run_id = _create_run("cccccccc-cccc-cccc-cccc-cccccccccccc")
    factory = app.state.session_factory
    with pytest.raises(RuntimeError):
        with operation_context(
            factory,
            agent_run_id=run_id,
            op_name="merge",
            params={"target": "main.silver.x", "on": ["id"], "strategy": "upsert"},
            target_table="main.silver.x",
        ) as recorder:
            recorder.input_sha = "f" * 64
            raise RuntimeError("boom")
    with factory() as session:
        row = session.scalar(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id)
        )
    assert row is not None
    assert row.error_message is not None
    assert "RuntimeError" in row.error_message
    assert row.input_sha == "f" * 64


def test_operation_context_skips_when_run_id_none() -> None:
    with operation_context(
        None,
        agent_run_id=None,
        op_name="sql",
        params={"query": "SELECT 1"},
    ) as recorder:
        recorder.rows_affected = 1
    # No row inserted; nothing to assert beyond the no-raise.


# ---------------------------------------------------------------------------
# event persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_event_persists_and_updates_outcome(monkeypatch) -> None:
    run_id = _create_run("dddddddd-dddd-dddd-dddd-dddddddddddd")
    factory = app.state.session_factory

    fake_dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr("pointlessql.services.agent_runs.events.dispatch_webhook", fake_dispatch)

    from pointlessql.settings import Settings

    settings = Settings()
    settings.agent_runs.webhook_url = "https://example.com/hook"

    await emit_agent_run_event(
        EVENT_TYPE_STARTED,
        {"id": run_id, "principal": "u@x", "agent_id": "a"},
        settings=settings,
        session_factory=factory,
    )

    with factory() as session:
        row = session.scalar(select(AgentRunEvent).where(AgentRunEvent.agent_run_id == run_id))
    assert row is not None
    assert row.outcome == "delivered"
    assert row.event_type == EVENT_TYPE_STARTED


@pytest.mark.asyncio
async def test_emit_event_marks_no_destination_without_url() -> None:
    run_id = _create_run("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    factory = app.state.session_factory

    from pointlessql.settings import Settings

    settings = Settings()
    settings.agent_runs.webhook_url = None  # type: ignore[assignment]

    await emit_agent_run_event(
        EVENT_TYPE_STARTED,
        {"id": run_id, "principal": "u@x", "agent_id": "a"},
        settings=settings,
        session_factory=factory,
    )

    with factory() as session:
        row = session.scalar(select(AgentRunEvent).where(AgentRunEvent.agent_run_id == run_id))
    assert row is not None
    assert row.outcome == "no_destination"


# ---------------------------------------------------------------------------
# run-detail page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detail_renders_operations_and_source_tabs() -> None:
    run_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    source = "import pql\n"
    async with _admin_client() as client:
        post = await client.post(
            "/api/agent-runs",
            json={
                "id": run_id,
                "notebook_path": "demo/x.py",
                "source": source,
                "runtime_versions": {"python": "3.14.0"},
            },
        )
        assert post.status_code == 200, post.text
        # Add one operation row for visibility.
        record_operation(
            app.state.session_factory,
            agent_run_id=run_id,
            op_name="sql",
            params={"query": "SELECT 1"},
            target_table=None,
            input_sha=None,
            rows_affected=1,
            delta_version_before=None,
            delta_version_after=None,
            started_at=datetime.datetime.now(datetime.UTC),
            finished_at=datetime.datetime.now(datetime.UTC),
            error_message=None,
        )
        page = await client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    body = page.text
    assert 'id="tab-ops-btn"' in body
    assert 'id="tab-source-btn"' in body
    assert 'id="tab-events-btn"' in body
    # Source bytes show up verbatim.
    assert "import pql" in body
    # Operations table renders the op_name badge.
    assert ">SQL<" in body or "sql</span>" in body.lower()
