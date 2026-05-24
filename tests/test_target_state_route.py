"""Tests for the target-state + recent-failures routes."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import AgentRunOperation
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``UnityCatalogClient.for_principal`` with a mock-backed factory.

    The cookie-authenticated test session sets ``effective_principal``,
    so :func:`get_uc_client` always lands on the ``for_principal``
    branch instead of ``app.state.uc_client``.  Patching the class
    method to return our mock keeps both branches addressable from
    a single fixture.
    """
    mock = MagicMock(spec=UnityCatalogClient)
    mock.get_table = AsyncMock(return_value={})
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: mock),  # type: ignore[arg-type]
    )
    return mock


async def _seed_run_with_op(
    client: httpx.AsyncClient,
    *,
    run_id: str,
    target: str,
    error_message: str | None = None,
    finished_at: dt.datetime | None = None,
) -> int:
    """Create a strict run + insert one ``agent_run_operations`` row.

    Returns the operation id.
    """
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
    factory = app.state.session_factory
    started = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    finished = finished_at or dt.datetime.now(dt.UTC)
    with factory() as session:
        row = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="write_table",
            params_json="{}",
            target_table=target,
            input_sha=None,
            rows_affected=42,
            delta_version_before=None,
            delta_version_after=3,
            started_at=started,
            finished_at=finished,
            error_message=error_message,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


# ---------------------------------------------------------------------------
# /api/pql/target-state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_target_state_returns_exists_false_when_uc_404s(
    uc_mock: MagicMock, admin_client: httpx.AsyncClient
) -> None:
    uc_mock.get_table.side_effect = CatalogNotFoundError("nope")
    response = await admin_client.get(
        "/api/pql/target-state", params={"table": "main.silver.orders_missing"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["table"] == "main.silver.orders_missing"
    assert payload["exists"] is False
    assert payload["schema"] is None
    assert payload["last_5_writes"] == []


@pytest.mark.asyncio
async def test_target_state_returns_schema_and_writes(
    uc_mock: MagicMock, admin_client: httpx.AsyncClient
) -> None:
    target = "main.silver.orders_state"
    uc_mock.get_table.return_value = {
        "name": "orders_state",
        "columns": [
            {"name": "id", "type_text": "BIGINT", "nullable": False, "comment": "pk"},
            {"name": "ts", "type_text": "TIMESTAMP", "nullable": True, "comment": None},
        ],
    }
    await _seed_run_with_op(
        admin_client,
        run_id="aaaa1111-1111-1111-1111-aaaaaaaaaaa1",
        target=target,
    )
    response = await admin_client.get("/api/pql/target-state", params={"table": target})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["exists"] is True
    assert payload["schema"][0]["name"] == "id"
    assert payload["schema"][0]["type_text"] == "BIGINT"
    writes = payload["last_5_writes"]
    assert len(writes) == 1
    assert writes[0]["op_name"] == "write_table"
    assert writes[0]["rows_affected"] == 42


@pytest.mark.asyncio
async def test_target_state_rejects_non_three_part_name(
    uc_mock: MagicMock, admin_client: httpx.AsyncClient
) -> None:
    response = await admin_client.get("/api/pql/target-state", params={"table": "not.three"})
    # ValidationError surfaces as 422 via the app's exception handler.
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/agent-runs/operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operations_filter_errored_only(admin_client: httpx.AsyncClient) -> None:
    target = "main.silver.flaky"
    # one ok, one errored — same target
    await _seed_run_with_op(
        admin_client,
        run_id="bbbb1111-2222-3333-4444-bbbbbbbbbbb1",
        target=target,
    )
    await _seed_run_with_op(
        admin_client,
        run_id="bbbb1111-2222-3333-4444-bbbbbbbbbbb2",
        target=target,
        error_message="Delta concurrent transaction",
    )
    response = await admin_client.get(
        "/api/agent-runs/operations",
        params={"target": target, "errored": "true"},
    )
    assert response.status_code == 200, response.text
    ops = response.json()["operations"]
    assert len(ops) == 1
    assert ops[0]["error_message"] == "Delta concurrent transaction"
    assert ops[0]["status"] == "error"
    assert ops[0]["target_table"] == target


@pytest.mark.asyncio
async def test_operations_rejects_bad_since(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/agent-runs/operations", params={"since": "yesterday"})
    assert response.status_code == 422
