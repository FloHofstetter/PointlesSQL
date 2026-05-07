"""Route-level tests for Sprint 52: export, cancel, timeout.

We deliberately mock the DuckDB connection for cancel/timeout so the
tests never actually block on a real long-running query — a real
interrupt test could hang the runner if the interrupt path regresses.
The production path is still exercised end-to-end via CSV + Parquet
export tests against a small Delta table.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_uc_mock(
    *,
    storage_location: str,
    effective: list[dict[str, Any]] | None = None,
) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
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
    df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "name": ["a", "b", "c", "d", "e"]})
    deltalake.write_deltalake(loc, df)
    return loc


# -- Export (real Delta, short queries — safe) ---------------------


async def test_csv_export_roundtrip(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    # Seed history by executing once.
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id, name FROM main.sales.orders ORDER BY id"},
    )
    assert resp.status_code == 200, resp.text

    # Look up the most recent history row.
    resp = await admin_client.get("/api/queries")
    entries = resp.json()
    assert entries, "expected history to have our execution"
    history_id = entries[0]["id"]

    resp = await admin_client.get(f"/api/sql/execute/{history_id}/download?format=csv")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="query-' in resp.headers.get("content-disposition", "")
    body = resp.text.splitlines()
    assert body[0] == "id,name"
    # 5 data rows + 1 header.
    assert len(body) == 6


async def test_parquet_export_roundtrip(orders_delta: str, admin_client: httpx.AsyncClient) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id FROM main.sales.orders"},
    )
    assert resp.status_code == 200, resp.text
    entries = (await admin_client.get("/api/queries")).json()
    history_id = entries[0]["id"]

    resp = await admin_client.get(f"/api/sql/execute/{history_id}/download?format=parquet")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/octet-stream"
    # The bytes should round-trip via pyarrow.parquet.
    table = pq.read_table(io.BytesIO(resp.content))
    assert table.column_names == ["id"]
    assert table.num_rows == 5


async def test_export_404_for_missing_history(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.get("/api/sql/execute/999999/download?format=csv")
    assert resp.status_code == 404


async def test_export_re_enforces_select(
    orders_delta: str, admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    # Admin seeds a history row (admin bypass is in effect).
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={"sql": "SELECT id FROM main.sales.orders"},
    )
    assert resp.status_code == 200, resp.text
    entries = (await admin_client.get("/api/queries")).json()
    history_id = entries[0]["id"]

    # Non-admin with no SELECT grant should not be able to download —
    # but first, they cannot even see the history row (owner = admin).
    # Swap the mock so effective perms stay empty for the non-admin.
    app.state.uc_client = _make_uc_mock(
        storage_location=orders_delta,
        effective=[],
    )
    resp = await non_admin_client.get(f"/api/sql/execute/{history_id}/download?format=csv")
    assert resp.status_code == 404  # collapsed with "not found"


# -- Cancel (mocked conn — safe, no real blocking query) -----------


async def test_cancel_calls_interrupt_on_registered_conn(admin_client: httpx.AsyncClient) -> None:
    # Register a mock conn directly in the app-state registry,
    # then hit the cancel endpoint.  Neither the route nor the
    # test ever runs a real DuckDB query in this path.
    mock_conn = MagicMock()
    registry: dict[str, Any] = {"test-qid-123": mock_conn}
    app.state._live_queries = registry

    resp = await admin_client.post("/api/sql/execute/test-qid-123/cancel")
    assert resp.status_code == 204
    mock_conn.interrupt.assert_called_once()


async def test_cancel_unknown_qid_is_idempotent(admin_client: httpx.AsyncClient) -> None:
    app.state._live_queries = {}
    resp = await admin_client.post("/api/sql/execute/never-existed/cancel")
    # Unknown → 204 by design so the client is idempotent with
    # the actual execute response race.
    assert resp.status_code == 204


async def test_cancel_swallows_interrupt_raising(admin_client: httpx.AsyncClient) -> None:
    # Some backends could raise from interrupt(); the endpoint
    # must not 500 on that — audit + 204 and move on.
    mock_conn = MagicMock()
    mock_conn.interrupt.side_effect = RuntimeError("mock backend died")
    app.state._live_queries = {"flaky-qid": mock_conn}
    resp = await admin_client.post("/api/sql/execute/flaky-qid/cancel")
    assert resp.status_code == 204


async def test_execute_returns_query_id_in_response(
    orders_delta: str, admin_client: httpx.AsyncClient
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    resp = await admin_client.post(
        "/api/sql/execute",
        json={
            "sql": "SELECT id FROM main.sales.orders LIMIT 1",
            "query_id": "client-chose-this",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Server echoes the client-supplied query_id so the Cancel
    # button can target it without re-reading from the URL.
    assert body["query_id"] == "client-chose-this"
