"""Tests for the data-product HTTP surface.

Covers the JSON list/detail/diff/lineage endpoints and the HTML
index + detail pages.  Uses the centralised ``admin_client`` /
``non_admin_client`` / ``anonymous_client`` fixtures from
``conftest.py``.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_yaml_and_load(tmp_path: Path) -> int:
    """Seed a yaml + load it into the cache; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        from sqlalchemy import select

        row = session.execute(select(DataProduct)).scalar_one()
        return row.id


# ---------------------------------------------------------------------------
# JSON: list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_seeded_products(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_yaml_and_load(tmp_path)
    res = await admin_client.get("/api/data-products")
    assert res.status_code == 200
    body = res.json()
    assert body["workspace_id"] == 1
    assert len(body["data_products"]) == 1
    p = body["data_products"][0]
    assert p["ref"] == "main.sales_gold"
    assert p["version"] == "1.0.0"
    assert p["sla_minutes"] == 60


@pytest.mark.asyncio
async def test_list_resolves_steward(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """When the yaml's steward_email matches a users row, the FK resolves."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            User(
                email="alice@example.com",
                display_name="Alice Steward",
                password_hash=None,
                is_admin=False,
                is_supervisor=False,
                is_auditor=False,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    _seed_yaml_and_load(tmp_path)

    body = (await admin_client.get("/api/data-products")).json()
    p = body["data_products"][0]
    assert p["steward"]["email"] == "alice@example.com"
    assert p["steward"]["display_name"] == "Alice Steward"


@pytest.mark.asyncio
async def test_list_anonymous_returns_401(
    tmp_path: Path,
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous JSON callers are blocked by the auth middleware."""
    _seed_yaml_and_load(tmp_path)
    res = await anonymous_client.get("/api/data-products")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# JSON: detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_returns_tables_and_events(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    product_id = _seed_yaml_and_load(tmp_path)

    # Seed an op row + a contract event so detail surfaces it.
    factory = app.state.session_factory
    from pointlessql.models import AgentRun, AgentRunOperation

    run_id = uuid.uuid4().hex
    with factory() as session:
        run = AgentRun(
            id=run_id,
            workspace_id=1,
            principal="seed",
            notebook_path="/tmp/seed.py",
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run_id,
            ordinal=1,
            op_name="write_table",
            params_json="{}",
            target_table="main.sales_gold.orders",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(op)
        session.flush()
        evt = DataProductContractEvent(
            agent_run_operation_id=op.id,
            data_product_id=product_id,
            outcome="compliant",
            details_json="{}",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(evt)
        session.commit()

    res = await admin_client.get("/api/data-products/main/sales_gold")
    assert res.status_code == 200
    body = res.json()
    assert body["product"]["ref"] == "main.sales_gold"
    assert len(body["tables"]) == 1
    assert body["tables"][0]["name"] == "orders"
    assert len(body["recent_events"]) == 1
    assert body["recent_events"][0]["outcome"] == "compliant"


@pytest.mark.asyncio
async def test_detail_404_for_unknown_product(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/api/data-products/main/missing")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# JSON: lineage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lineage_returns_empty_graph_when_no_edges(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """Without lineage_row_edges the graph contains only the table nodes."""
    _seed_yaml_and_load(tmp_path)
    res = await admin_client.get("/api/data-products/main/sales_gold/lineage")
    assert res.status_code == 200
    body = res.json()
    assert any(node["data"]["id"] == "main.sales_gold.orders" for node in body["nodes"])
    assert body["edges"] == []


# ---------------------------------------------------------------------------
# JSON: reload (admin-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_requires_admin(
    non_admin_client: httpx.AsyncClient,
) -> None:
    res = await non_admin_client.post("/api/data-products/reload")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reload_400_when_search_paths_empty(
    admin_client: httpx.AsyncClient,
) -> None:
    """Reload errors clearly when no yaml_search_paths are configured."""
    res = await admin_client.post("/api/data-products/reload")
    body = res.json()
    assert res.status_code == 400
    assert "yaml_search_paths" in json.dumps(body)


# ---------------------------------------------------------------------------
# HTML: index + detail pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_html_returns_200(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_yaml_and_load(tmp_path)
    res = await admin_client.get("/data-products")
    assert res.status_code == 200
    assert "Data Products" in res.text


@pytest.mark.asyncio
async def test_detail_html_returns_200(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_yaml_and_load(tmp_path)
    res = await admin_client.get("/data-products/main/sales_gold")
    assert res.status_code == 200
    assert "main.sales_gold" in res.text


@pytest.mark.asyncio
async def test_html_anonymous_redirects(
    anonymous_client: httpx.AsyncClient,
) -> None:
    res = await anonymous_client.get("/data-products")
    assert res.status_code in (303, 307)
    assert "/auth/login" in res.headers.get("location", "")
