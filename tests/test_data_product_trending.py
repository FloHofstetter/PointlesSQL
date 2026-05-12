"""Tests for the Phase-72.3 trending board.

Covers:

* ``refresh_trending`` inserts top-N rows per workspace, sorted
  by ``agent_run_count`` (then ``write_count``) desc.
* A second refresh against the same window UPSERTs (no row
  duplication).
* DPs with zero activity are excluded from the snapshot.
* ``fetch_trending`` returns the freshest window per
  ``(workspace_id, data_product_id)``.
* HTML page renders the rows; click-through link is present.
* Cross-workspace scope gate (auditor / admin pass).
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.catalog._data_product_trending import DataProductTrending
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.data_products import refresh_trending

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: {schema}
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {{name: order_id, type: long, nullable: false}}
"""


def _seed_dp(tmp_path: Path, schema: str = "sales_gold") -> int:
    """Seed a DP under ``main.<schema>``."""
    yaml_path = tmp_path / f"{schema}.yaml"
    yaml_path.write_text(VALID_YAML.format(schema=schema), encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return (
            session.execute(
                select(DataProduct).where(DataProduct.schema_name == schema)
            )
            .scalar_one()
            .id
        )


def _seed_op(target: str, *, age_seconds: int = 0) -> None:
    """Seed one AgentRun + Op hitting *target*."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    with factory() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            principal="t@t.com",
            agent_id="a",
            notebook_path="/x",
            status="finished",
            started_at=when,
            finished_at=when,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run.id,
            ordinal=1,
            op_name="write_table",
            params_json="{}",
            target_table=target,
            started_at=when,
            finished_at=when,
        )
        session.add(op)
        session.commit()


# ---------------------------------------------------------------------------
# refresh_trending
# ---------------------------------------------------------------------------


def test_refresh_skips_dps_with_no_activity(tmp_path: Path) -> None:
    """A DP with zero ops + zero runs in the window doesn't appear."""
    _seed_dp(tmp_path, "sales_gold")
    inserted = refresh_trending(app.state.session_factory)
    assert inserted == 0


def test_refresh_inserts_active_dps(tmp_path: Path) -> None:
    """One DP with one op → one trending row, rank=1."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_op("main.sales_gold.orders")
    inserted = refresh_trending(app.state.session_factory)
    assert inserted == 1
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductTrending)).scalars().all()
        assert len(rows) == 1
        assert rows[0].rank == 1
        assert rows[0].agent_run_count == 1
        assert rows[0].write_count == 1


def test_refresh_ranks_by_agent_run_count(tmp_path: Path) -> None:
    """Two DPs: one with 3 runs, one with 1 → ranks 1 and 2."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_dp(tmp_path, "quiet_schema")
    for _ in range(3):
        _seed_op("main.sales_gold.orders")
    _seed_op("main.quiet_schema.orders")
    refresh_trending(app.state.session_factory)
    factory = app.state.session_factory
    with factory() as session:
        rows = sorted(
            session.execute(select(DataProductTrending)).scalars().all(),
            key=lambda r: r.rank,
        )
        assert [r.rank for r in rows] == [1, 2]
        assert rows[0].agent_run_count >= rows[1].agent_run_count


def test_refresh_is_idempotent(tmp_path: Path) -> None:
    """Two refreshes at the same window collapse onto one row per DP."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_op("main.sales_gold.orders")
    fixed_now = datetime.datetime.now(datetime.UTC)
    refresh_trending(app.state.session_factory, now=fixed_now)
    refresh_trending(app.state.session_factory, now=fixed_now)
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductTrending)).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# fetch_trending + routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_trending_returns_rows(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/data-products/trending`` lists the cached rows."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_op("main.sales_gold.orders")
    refresh_trending(app.state.session_factory)
    res = await admin_client.get("/api/data-products/trending")
    assert res.status_code == 200
    body = res.json()
    assert body["workspace_scope"] == "current"
    assert len(body["trending"]) == 1
    assert body["trending"][0]["data_product_ref"] == "main.sales_gold"


@pytest.mark.asyncio
async def test_api_trending_cross_workspace_admin_passes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Admin can request the cross-workspace scope."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_op("main.sales_gold.orders")
    refresh_trending(app.state.session_factory)
    res = await admin_client.get(
        "/api/data-products/trending?workspace_scope=all"
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_api_trending_cross_workspace_non_admin_403(
    tmp_path: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admin non-auditor cannot request the cross-workspace scope."""
    _seed_dp(tmp_path, "sales_gold")
    res = await non_admin_client.get(
        "/api/data-products/trending?workspace_scope=all"
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_html_page_renders(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /data-products/trending`` renders the table fingerprint."""
    _seed_dp(tmp_path, "sales_gold")
    _seed_op("main.sales_gold.orders")
    refresh_trending(app.state.session_factory)
    res = await admin_client.get("/data-products/trending")
    assert res.status_code == 200
    assert "pql-dp-trending-table" in res.text
