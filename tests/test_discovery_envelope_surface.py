"""Discovery envelope carries the Surface-Welle additions.

Locks in the additive contract every page consumer relies on: new
blocks (``policy_modules``, ``contract_tests``, ``fixtures``, ``cost``)
plus the new policy fields (``iso8601_enforcement``,
``linked_policy_module_ids``, ``breaking_change_policy``,
``quota_enforcement``, ``max_cost_per_day``, ``max_queries_per_hour``)
and the per-port ``version_semver`` + ``schema_history`` channel.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductOutputPort,
    DataProductPolicy,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_product_with_port(catalog: str, schema: str) -> int:
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
        session.flush()
        port = DataProductOutputPort(
            data_product_id=int(product.id),
            name="gold",
            kind="sql",
            format="delta",
            location=f"{catalog}.{schema}.gold",
            description="",
            version_semver="2.1.0",
            created_at=_now(),
        )
        session.add(port)
        policy = DataProductPolicy(
            data_product_id=int(product.id),
            quota_enforcement="warn",
            max_queries_per_hour=100,
            max_cost_per_day=42,
            breaking_change_policy="warn",
            iso8601_enforcement="warn",
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(policy)
        session.commit()
        return int(product.id)


@pytest.mark.asyncio
async def test_discovery_envelope_carries_surface_welle_blocks() -> None:
    _seed_product_with_port("surface", "envelope")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/surface/envelope/discovery")
    assert res.status_code == 200, res.text
    body = res.json()

    assert "policy_modules" in body
    assert isinstance(body["policy_modules"], list)
    assert "contract_tests" in body
    assert isinstance(body["contract_tests"], list)
    assert "fixtures" in body
    assert isinstance(body["fixtures"], list)
    assert "cost" in body
    assert "last_7d_total_estimated_cost" in body["cost"]
    assert "last_7d_query_count" in body["cost"]

    policies = body["policies"]
    assert policies["iso8601_enforcement"] == "warn"
    assert policies["breaking_change_policy"] == "warn"
    assert policies["quota_enforcement"] == "warn"
    assert policies["max_cost_per_day"] is not None
    assert policies["max_queries_per_hour"] == 100
    assert policies["linked_policy_module_ids"] == []

    ports = body["output_ports"]
    assert ports[0]["version_semver"] == "2.1.0"
    assert "schema_history" in ports[0]
    assert isinstance(ports[0]["schema_history"], list)
