"""Tests for the Sprint 13.11.3 ``GET /api/pql/lineage`` route."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(spec=UnityCatalogClient)
    mock.get_lineage = AsyncMock(return_value={"upstream": {}, "downstream": {}})
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: mock),  # type: ignore[arg-type]
    )
    return mock


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


@pytest.mark.asyncio
async def test_lineage_returns_combined_graph(uc_mock: MagicMock) -> None:
    uc_mock.get_lineage.return_value = {
        "upstream": {
            "root": "main.silver.orders",
            "direction": "upstream",
            "nodes": [{"securable_id": "id1", "full_name": "main.bronze.orders_raw", "depth": 1}],
            "edges": [],
        },
        "downstream": {
            "root": "main.silver.orders",
            "direction": "downstream",
            "nodes": [{"securable_id": "id2", "full_name": "main.gold.summary", "depth": 1}],
            "edges": [],
        },
    }
    async with _admin_client() as client:
        response = await client.get(
            "/api/pql/lineage",
            params={"table": "main.silver.orders", "depth": 2},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["table"] == "main.silver.orders"
    assert payload["depth"] == 2
    assert payload["upstream"]["nodes"][0]["full_name"] == "main.bronze.orders_raw"
    assert payload["downstream"]["nodes"][0]["full_name"] == "main.gold.summary"
    uc_mock.get_lineage.assert_awaited_once_with("main.silver.orders", depth=2)


@pytest.mark.asyncio
async def test_lineage_rejects_two_part_name(uc_mock: MagicMock) -> None:
    async with _admin_client() as client:
        response = await client.get("/api/pql/lineage", params={"table": "main.silver"})
    assert response.status_code == 422
    uc_mock.get_lineage.assert_not_called()


@pytest.mark.asyncio
async def test_lineage_rejects_depth_above_max(uc_mock: MagicMock) -> None:
    async with _admin_client() as client:
        response = await client.get(
            "/api/pql/lineage",
            params={"table": "main.silver.orders", "depth": 99},
        )
    # FastAPI Query(le=5) rejects with 422 before our handler runs.
    assert response.status_code == 422
    uc_mock.get_lineage.assert_not_called()
