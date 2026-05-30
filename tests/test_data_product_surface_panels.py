"""Per-product Surface-Welle panels render under standard auth.

Smoke-tests the new Contract-Tests tab on data_product.html, plus
verifies that the Governance discovery envelope carries the cost
block the new Governance card relies on.
"""

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
async def test_data_product_page_renders_contract_tests_tab() -> None:
    _seed_product("surface", "contract_tab")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/data-products/surface/contract_tab")
    assert res.status_code == 200, res.text
    body = res.text
    assert 'data-pql-tab-key="contract-tests"' in body
    assert "tab-contract-tests" in body
    assert "dataProductContractTests" in body


@pytest.mark.asyncio
async def test_governance_card_consumes_new_cost_block() -> None:
    _seed_product("surface", "gov_cost_block")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get(
            "/api/data-products/surface/gov_cost_block/discovery"
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "cost" in body
    assert "last_7d_total_estimated_cost" in body["cost"]
    policies = body["policies"]
    assert "quota_enforcement" in policies
