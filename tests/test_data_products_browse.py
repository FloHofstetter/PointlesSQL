"""Tests for the Phase-71.6 enriched data-product browse listing.

Covers ``GET /api/data-products`` carrying the new aggregate
fields (``follow_count``, ``comment_count_7d``, ``has_readme``,
``freshness_status``), the SLA-boundary flip from ``on_time`` →
``stale``, and the new HTML template fingerprint
(``pql-dp-table`` + ``pql-dp-filter-chips``).
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_products import DataProduct

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


@pytest.fixture
async def anonymous_client() -> AsyncIterator[httpx.AsyncClient]:
    """``httpx.AsyncClient`` with no auth cookie."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + load it; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_carries_new_aggregate_fields(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Every product carries follow_count + comment_count_7d + has_readme + freshness_status."""
    _seed_product(tmp_path)
    body = (await admin_client.get("/api/data-products")).json()
    product = body["data_products"][0]
    for key in (
        "avg_stars",
        "review_count",
        "follow_count",
        "comment_count_7d",
        "has_readme",
        "freshness_status",
    ):
        assert key in product, f"missing field {key} in {product.keys()}"


@pytest.mark.asyncio
async def test_follow_count_reflects_follower(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A new follower bumps ``follow_count`` on the listing."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    body = (await admin_client.get("/api/data-products")).json()
    assert body["data_products"][0]["follow_count"] == 1


@pytest.mark.asyncio
async def test_comment_count_7d_counts_only_recent_live(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """``comment_count_7d`` ignores soft-deleted comments."""
    _seed_product(tmp_path)
    posted = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "fresh"},
    )
    body = (await admin_client.get("/api/data-products")).json()
    assert body["data_products"][0]["comment_count_7d"] == 1
    # soft-delete and re-check
    await admin_client.delete(
        f"/api/data-products/main/sales_gold/comments/{posted.json()['id']}"
    )
    body2 = (await admin_client.get("/api/data-products")).json()
    assert body2["data_products"][0]["comment_count_7d"] == 0


@pytest.mark.asyncio
async def test_has_readme_flips_on_put(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``has_readme`` is false until a PUT lands."""
    _seed_product(tmp_path)
    pre = (await admin_client.get("/api/data-products")).json()
    assert pre["data_products"][0]["has_readme"] is False
    await admin_client.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "first"},
    )
    post = (await admin_client.get("/api/data-products")).json()
    assert post["data_products"][0]["has_readme"] is True


# ---------------------------------------------------------------------------
# Freshness boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_freshness_status_on_time_then_stale(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Within SLA → ``on_time``; manually backdate ``last_loaded_at`` to flip."""
    _seed_product(tmp_path)
    body = (await admin_client.get("/api/data-products")).json()
    assert body["data_products"][0]["freshness_status"] == "on_time"

    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        # Push last_loaded_at 2h into the past; sla_minutes=60 → stale.
        dp.last_loaded_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            hours=2
        )
        session.add(dp)
        session.commit()
    body2 = (await admin_client.get("/api/data-products")).json()
    assert body2["data_products"][0]["freshness_status"] == "stale"


@pytest.mark.asyncio
async def test_freshness_status_no_sla(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Products without an SLA report ``freshness_status='no_sla'``."""
    _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        dp.sla_minutes = None
        session.add(dp)
        session.commit()
    body = (await admin_client.get("/api/data-products")).json()
    assert body["data_products"][0]["freshness_status"] == "no_sla"


# ---------------------------------------------------------------------------
# Template fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_page_renders_new_table_and_chips(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The reworked browse page ships the table + chip selectors."""
    _seed_product(tmp_path)
    page = await admin_client.get("/data-products")
    assert page.status_code == 200
    assert "pql-dp-filter-chips" in page.text
    assert "pql-dp-table" in page.text
    assert "pql-dp-view-toggle" in page.text
