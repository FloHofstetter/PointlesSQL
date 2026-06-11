"""Tests for the metric-view routes (facade stubbed, compiler real)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api import metric_views_routes as routes_module
from pointlessql.api.main import app
from pointlessql.pql._types import SQLResult

_VIEW = {
    "full_name": "shop.gold.revenue",
    "name": "revenue",
    "catalog_name": "shop",
    "schema_name": "gold",
    "source_table_full_name": "shop.gold.orders",
    "comment": None,
    "spec": {
        "dimensions": [{"name": "region", "expr": "region"}],
        "measures": [{"name": "revenue", "expr": "sum(amount)"}],
    },
}


def _client(cookies: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


@pytest.mark.asyncio
async def test_list_and_get_proxy_the_facade(uc_client_stub) -> None:
    uc_client_stub.list_metric_views.return_value = [_VIEW]
    uc_client_stub.get_metric_view.return_value = _VIEW
    async with _client(app.state._test_auth_cookie) as client:
        listing = await client.get("/api/metric-views?catalog_name=shop&schema_name=gold")
        assert listing.status_code == 200
        assert listing.json()["metric_views"][0]["full_name"] == "shop.gold.revenue"
        detail = await client.get("/api/metric-views/shop.gold.revenue")
        assert detail.json()["name"] == "revenue"
    uc_client_stub.list_metric_views.assert_awaited_once_with("shop", "gold")


@pytest.mark.asyncio
async def test_query_compiles_and_executes(uc_client_stub, monkeypatch) -> None:
    uc_client_stub.get_metric_view.return_value = _VIEW

    seen: dict[str, Any] = {}

    async def _fake_resolve(sql: str, **kwargs: Any) -> tuple[dict[str, str], dict[str, Any]]:
        seen["sql"] = sql
        return {"shop.gold.orders": "memory://orders"}, {}

    def _fake_exec(
        sql: str, approved: dict[str, str], max_rows: int, policies: Any = None
    ) -> SQLResult:
        return SQLResult(
            columns=[{"name": "region", "type": "VARCHAR"}, {"name": "revenue", "type": "BIGINT"}],
            rows=[["emea", 30]],
            row_count=1,
            truncated=False,
            duration_ms=2,
            executed_sql=sql,
            rewritten_sql=sql,
            referenced_tables=["shop.gold.orders"],
        )

    monkeypatch.setattr(routes_module, "resolve_select_context", _fake_resolve)
    monkeypatch.setattr(routes_module, "_run_metric_sql", _fake_exec)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            "/api/metric-views/shop.gold.revenue/query",
            json={"dimensions": ["region"], "measures": ["revenue"], "limit": 10},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == [["emea", 30]]
    assert 'SUM(amount) AS "revenue"' in body["sql"]
    assert "GROUP BY 1" in seen["sql"]


@pytest.mark.asyncio
async def test_query_rejects_unknown_measure(uc_client_stub) -> None:
    uc_client_stub.get_metric_view.return_value = _VIEW
    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            "/api/metric-views/shop.gold.revenue/query",
            json={"measures": ["nope"]},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_browser_page_renders() -> None:
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get("/metric-views")
    assert page.status_code == 200
    assert 'x-data="metricViews()"' in page.text
    assert "metric_views.js" in page.text
