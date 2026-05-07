"""Per-run audit row tests for GET /api/sql/explain (Phase 39 Sprint 39.1).

When the explain endpoint is called from inside an agent run (the
``X-Agent-Run-Id`` header is present), an ``agent_run_operations`` row
with ``op_name='sql_explain'`` is written so an auditor can see what
the agent saw before deciding to execute or rewrite. The interactive
path (no header) stays as it was — only the install-wide ``audit_log``
row fires.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_uc_mock(*, storage_location: str) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=[])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    deltalake.write_deltalake(loc, df)
    return loc


def _seed_run(workspace_id: int = 1) -> str:
    """Insert one minimal AgentRun and return its UUID."""
    run_id = str(uuid.uuid4())
    factory: Any = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal="test@test.com",
                agent_id="test-agent",
                notebook_path="/tmp/agent.py",
                status="RUNNING",
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return run_id


def _ops_for_run(run_id: str) -> list[AgentRunOperation]:
    factory: Any = app.state.session_factory
    with factory() as session:
        return list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == run_id)
                .order_by(AgentRunOperation.ordinal)
            )
        )


async def test_explain_with_agent_run_writes_per_run_audit(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    """X-Agent-Run-Id header → one sql_explain ops row with cost details."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    run_id = _seed_run()

    resp = await admin_client.get(
        "/api/sql/explain",
        params={"sql": "SELECT id, name FROM main.sales.orders ORDER BY id"},
        headers={"X-Agent-Run-Id": run_id},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "plan" in body
    assert body["needs_approval"] is False  # tiny table

    ops = _ops_for_run(run_id)
    assert len(ops) == 1, f"expected one sql_explain row, got {len(ops)}"
    op = ops[0]
    assert op.op_name == "sql_explain"
    assert op.target_table is None
    assert op.rows_affected is None
    assert op.error_message is None
    import json as _json

    params = _json.loads(op.params_json)
    assert "sql_hash" in params
    assert params["referenced_tables"] == ["main.sales.orders"]
    assert params["needs_approval"] is False
    assert "cost" in params
    assert "max_cardinality" in params
    assert "join_depth" in params
    assert "threshold" in params


async def test_explain_without_header_writes_no_per_run_audit(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    """No X-Agent-Run-Id → no agent_run_operations row, only audit_log."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    run_id = _seed_run()  # exists, but caller doesn't reference it

    resp = await admin_client.get(
        "/api/sql/explain",
        params={"sql": "SELECT id, name FROM main.sales.orders"},
    )

    assert resp.status_code == 200, resp.text
    ops = _ops_for_run(run_id)
    assert ops == [], "interactive call must not write agent_run_operations rows"


async def test_explain_with_malformed_run_id_still_succeeds(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    """Bad UUID demoted to no-op for audit; explain itself still 200s."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)

    resp = await admin_client.get(
        "/api/sql/explain",
        params={"sql": "SELECT id FROM main.sales.orders"},
        headers={"X-Agent-Run-Id": "not-a-uuid"},
    )

    assert resp.status_code == 200, resp.text
    # No matching run, and no row was attempted.  Sweep all ops:
    factory: Any = app.state.session_factory
    with factory() as session:
        rows = session.scalars(select(AgentRunOperation)).all()
    assert rows == []


async def test_explain_failure_inside_run_records_error_row(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    """SQL parse failure with X-Agent-Run-Id → ops row carries error_message."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    run_id = _seed_run()

    resp = await admin_client.get(
        "/api/sql/explain",
        params={"sql": "this is not sql"},
        headers={"X-Agent-Run-Id": run_id},
    )

    assert resp.status_code >= 400  # parse failure surfaces as SQLExecutionError

    ops = _ops_for_run(run_id)
    assert len(ops) == 1
    op = ops[0]
    assert op.op_name == "sql_explain"
    assert op.error_message is not None
    assert "SQLExecutionError" in op.error_message or "parse" in op.error_message.lower()
