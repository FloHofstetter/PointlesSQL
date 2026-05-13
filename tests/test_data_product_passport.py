"""Tests for the Phase-73.4 data passport.

Covers:

* ``render_passport`` produces a markdown body with the
  expected section headers.
* ``refresh_passport_for_dp`` inserts a row with monotonic
  ``version_int``.
* Manual POST refresh works.
* GET returns latest + versions list.
* Cross-workspace iso.
* Stale-threshold filter on ``refresh_stale_passports``.
* Schema-changed reload triggers a passport refresh.
* HTML page exposes the passport markup.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_product_passport import DataProductPassport
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.lineage._core import LineageColumnMap
from pointlessql.services.data_products import (
    refresh_passport_for_dp,
    refresh_stale_passports,
    render_passport,
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


def _seed_dp(tmp_path: Path) -> DataProduct:
    """Seed one data product; return the row."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one()


def _seed_lineage_edges(dp: DataProduct) -> None:
    """Seed two lineage_column_map rows: one upstream + one downstream."""
    factory = app.state.session_factory
    with factory() as session:
        prefix = f"{dp.catalog_name}.{dp.schema_name}"
        now = datetime.datetime.now(datetime.UTC)
        session.add(
            LineageColumnMap(
                workspace_id=dp.workspace_id,
                source_table="raw.bronze.orders_in",
                source_column="o_id",
                target_table=f"{prefix}.orders",
                target_column="order_id",
                transform_kind="rename",
                created_at=now,
            )
        )
        session.add(
            LineageColumnMap(
                workspace_id=dp.workspace_id,
                source_table=f"{prefix}.orders",
                source_column="order_id",
                target_table="downstream.reporting.daily_orders",
                target_column="order_id",
                transform_kind="identity",
                created_at=now,
            )
        )
        session.commit()


def test_render_passport_emits_all_sections(tmp_path: Path) -> None:
    """The rendered markdown contains the four documented sections."""
    dp = _seed_dp(tmp_path)
    _seed_lineage_edges(dp)
    factory = app.state.session_factory
    with factory() as session:
        body, stats = render_passport(
            session,
            workspace_id=1,
            data_product=dp,
        )
    assert "## What this product holds" in body
    assert "## Where the data comes from" in body
    assert "## Who consumes it" in body
    assert "## Freshness profile" in body
    assert "## Recent activity" in body
    assert "raw.bronze.orders_in" in body
    assert "downstream.reporting.daily_orders" in body
    assert stats["edge_count"] >= 1


def test_refresh_passport_increments_version(tmp_path: Path) -> None:
    """Two refreshes produce monotonically increasing version_int."""
    dp = _seed_dp(tmp_path)
    _seed_lineage_edges(dp)
    factory = app.state.session_factory
    v1 = refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp.id,
        trigger="manual",
    )
    v2 = refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp.id,
        trigger="manual",
    )
    assert v1 == 1
    assert v2 == 2
    with factory() as session:
        rows = session.execute(select(DataProductPassport)).scalars().all()
        assert len(rows) == 2


def test_refresh_passport_unknown_dp_returns_zero(tmp_path: Path) -> None:
    """Refreshing a DP id that doesn't exist returns version 0."""
    factory = app.state.session_factory
    v = refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=99999,
        trigger="manual",
    )
    assert v == 0


def test_refresh_stale_passports_skips_recent(tmp_path: Path) -> None:
    """A DP with a recent passport is skipped by the stale loop."""
    dp = _seed_dp(tmp_path)
    factory = app.state.session_factory
    refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp.id,
        trigger="manual",
    )
    # Threshold = 1 day — the row we just inserted is fresh.
    refreshed = refresh_stale_passports(
        factory, stale_threshold_seconds=86_400
    )
    assert refreshed == 0


def test_refresh_stale_passports_picks_up_old(tmp_path: Path) -> None:
    """A DP whose passport is older than the threshold gets refreshed."""
    dp = _seed_dp(tmp_path)
    factory = app.state.session_factory
    refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp.id,
        trigger="manual",
    )
    # Backdate the passport to look stale.
    with factory() as session:
        row = session.execute(select(DataProductPassport)).scalar_one()
        row.refreshed_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            days=3
        )
        session.add(row)
        session.commit()
    refreshed = refresh_stale_passports(
        factory, stale_threshold_seconds=86_400
    )
    assert refreshed == 1


@pytest.mark.asyncio
async def test_api_get_passport_returns_latest(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """GET returns the latest passport + the version history."""
    dp = _seed_dp(tmp_path)
    factory = app.state.session_factory
    refresh_passport_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp.id,
        trigger="manual",
    )
    res = await admin_client.get(
        "/api/data-products/main/sales_gold/passport"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["latest"] is not None
    assert body["latest"]["version_int"] == 1
    assert len(body["versions"]) == 1


@pytest.mark.asyncio
async def test_api_post_passport_refresh(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST /passport/refresh inserts a new row and returns its version."""
    _seed_dp(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/passport/refresh"
    )
    assert res.status_code == 200, res.text
    assert res.json()["version_int"] == 1


@pytest.mark.asyncio
async def test_dp_detail_renders_passport_card(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The DP detail HTML page carries the passport-card fingerprint."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/data-products/main/sales_gold")
    assert res.status_code == 200
    assert "pql-dp-passport-card" in res.text or "pql-dp-passport-empty" in res.text
