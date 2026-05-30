"""GET equivalent of the point-in-time-read endpoint takes ``?as_of=``."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product(catalog: str, schema: str) -> int:
    """Seed a data product owned by no specific steward (admin reads it)."""
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    with _factory()() as session:
        product = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(product)
        session.commit()
        return int(product.id)


@pytest.mark.asyncio
async def test_point_in_time_read_get_resolves_for_admin() -> None:
    _seed_product("f2", "as_of_get")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get(
            "/api/data-products/f2/as_of_get/point-in-time-read",
            params={"as_of": "2026-01-01T00:00:00Z"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "when" in body
    assert body["when"].startswith("2026-01-01")
    assert "products" in body


@pytest.mark.asyncio
async def test_point_in_time_read_get_rejects_bad_timestamp() -> None:
    _seed_product("f2", "as_of_get_bad")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get(
            "/api/data-products/f2/as_of_get_bad/point-in-time-read",
            params={"as_of": "not-a-timestamp"},
        )
    assert res.status_code == 400
