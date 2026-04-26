"""Smoke tests for ``GET /api/lineage/value-changes`` (Sprint 15.7.4).

Sets up synthetic ``lineage_value_changes`` rows and exercises the
JSON handler.  The HTML row-trace surface that joins these rows into
the existing per-step display is exercised by the live replay in
Sprint 15.7.5.
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
    LineageValueChange,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(spec=UnityCatalogClient)
    mock.get_table = AsyncMock(return_value={})
    mock.get_effective_permissions = AsyncMock(return_value=[])
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: mock),  # type: ignore[arg-type]
    )
    # Same module-level get_session_factory shim as the column-trace
    # smoke tests (Sprint 15.6.4).
    import pointlessql.db as _db

    monkeypatch.setattr(_db, "get_session_factory", lambda: app.state.session_factory)
    return mock


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_value_changes() -> tuple[str, int]:
    """Insert one merge op + two value-change rows on (silver.orders, row-A)."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-15.7-test",
                notebook_path="value_change_route.py",
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
            target_table="main.silver.orders",
            started_at=now,
        )
        s.add(merge_op)
        s.commit()
        s.refresh(merge_op)
        op_id = merge_op.id
        s.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table="main.silver.orders",
                target_row_id="row-A",
                target_column="unit_price",
                old_value="2.5",
                new_value="2.51",
                created_at=now,
            )
        )
        s.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table="main.silver.orders",
                target_row_id="row-A",
                target_column="qty",
                old_value="1",
                new_value="2",
                created_at=now,
            )
        )
        s.commit()
        return run_id, op_id


@pytest.mark.asyncio
async def test_value_changes_returns_two_changes(uc_mock: MagicMock) -> None:
    _seed_value_changes()
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/value-changes",
            params={"table": "main.silver.orders", "row_id": "row-A"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["table"] == "main.silver.orders"
    assert payload["row_id"] == "row-A"
    changes = payload["changes"]
    assert len(changes) == 2
    cols = {c["target_column"] for c in changes}
    assert cols == {"unit_price", "qty"}
    unit_price_change = next(c for c in changes if c["target_column"] == "unit_price")
    assert unit_price_change["old_value"] == "2.5"
    assert unit_price_change["new_value"] == "2.51"


@pytest.mark.asyncio
async def test_value_changes_column_filter_narrows(uc_mock: MagicMock) -> None:
    _seed_value_changes()
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/value-changes",
            params={
                "table": "main.silver.orders",
                "row_id": "row-A",
                "column": "unit_price",
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["column"] == "unit_price"
    assert len(payload["changes"]) == 1
    assert payload["changes"][0]["target_column"] == "unit_price"


@pytest.mark.asyncio
async def test_value_changes_unknown_row_returns_empty(uc_mock: MagicMock) -> None:
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/value-changes",
            params={"table": "main.silver.orders", "row_id": "never-existed"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["changes"] == []


@pytest.mark.asyncio
async def test_value_changes_rejects_empty_row_id(uc_mock: MagicMock) -> None:
    async with _admin_client() as client:
        response = await client.get(
            "/api/lineage/value-changes",
            params={"table": "main.silver.orders", "row_id": ""},
        )
    assert response.status_code == 400
