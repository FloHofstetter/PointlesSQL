"""Smoke tests for ``GET /api/lineage/column-trace`` (Sprint 15.6.4).

Sets up synthetic ``lineage_column_map`` rows and exercises the
JSON walkback handler.  The HTML page is exercised by the live
replay in Sprint 15.6.5.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageColumnMap,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(spec=UnityCatalogClient)
    # check_privilege uses get_effective_permissions internally — admin path bypasses anyway
    mock.get_table = AsyncMock(return_value={})
    mock.get_effective_permissions = AsyncMock(return_value=[])
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: mock),  # type: ignore[arg-type]
    )
    # The row/column-trace routes call ``pointlessql.db.get_session_factory``
    # rather than ``request.app.state.session_factory`` — the conftest sets
    # the latter, so monkeypatch the former to delegate.
    import pointlessql.db as _db
    monkeypatch.setattr(_db, "get_session_factory", lambda: app.state.session_factory)
    return mock


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_column_map_chain() -> tuple[str, int, int]:
    """Insert a 2-hop column-map chain bronze.qty → silver.qty → gold.units_sold."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-15.6-test",
                notebook_path="column_trace_route.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        merge_op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.t",
            started_at=now,
        )
        agg_op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=2,
            op_name="aggregate",
            params_json="{}",
            target_table="main.gold.t",
            started_at=now,
        )
        s.add(merge_op)
        s.add(agg_op)
        s.commit()
        s.refresh(merge_op)
        s.refresh(agg_op)
        s.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=merge_op.id,
                source_table="main.bronze.t",
                source_column="qty",
                target_table="main.silver.t",
                target_column="qty",
                transform_kind="identity",
                created_at=now,
            )
        )
        s.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=agg_op.id,
                source_table="main.silver.t",
                source_column="qty",
                target_table="main.gold.t",
                target_column="units_sold",
                transform_kind="aggregate",
                transform_detail="sum",
                created_at=now,
            )
        )
        s.commit()
        return run_id, merge_op.id, agg_op.id


@pytest.mark.asyncio
async def test_column_trace_walks_back_two_hops(uc_mock: MagicMock) -> None:
    _seed_column_map_chain()
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/column-trace",
            params={"table": "main.gold.t", "column": "units_sold"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["table"] == "main.gold.t"
    assert payload["column"] == "units_sold"
    steps = payload["steps"]
    assert len(steps) == 3
    assert (steps[0]["table"], steps[0]["column"]) == ("main.gold.t", "units_sold")
    assert (steps[1]["table"], steps[1]["column"]) == ("main.silver.t", "qty")
    assert (steps[2]["table"], steps[2]["column"]) == ("main.bronze.t", "qty")
    assert steps[0]["predecessors"][0]["transform_kind"] == "aggregate"
    assert steps[0]["predecessors"][0]["transform_detail"] == "sum"


@pytest.mark.asyncio
async def test_column_trace_unknown_column_returns_lone_step(uc_mock: MagicMock) -> None:
    _seed_column_map_chain()
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/column-trace",
            params={"table": "main.gold.t", "column": "does_not_exist"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["predecessors"] == []


@pytest.mark.asyncio
async def test_column_trace_rejects_empty_column(uc_mock: MagicMock) -> None:
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/column-trace",
            params={"table": "main.gold.t", "column": ""},
        )
    assert response.status_code == 400
