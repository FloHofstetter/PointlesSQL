"""Tests for the Phase-71.2 data-product reviews surface.

Covers PUT upsert idempotency, DELETE round-trip, 1..5 stars
CHECK, summary aggregation, browse-page enrichment, and cross-
workspace isolation.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.workspace import Workspace, WorkspaceMember

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



def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + load it into the cache; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        row = session.execute(select(DataProduct)).scalar_one()
        return row.id


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_creates_review(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """First PUT creates a row + serialises it back."""
    _seed_product(tmp_path)
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 4, "body_md": "Good!"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stars"] == 4
    assert body["body_md"] == "Good!"
    assert body["dp_version_at_review"] == "1.0.0"


@pytest.mark.asyncio
async def test_second_put_updates_in_place(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Second PUT by same user moves stars + updated_at, no second row."""
    _seed_product(tmp_path)
    first = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 3, "body_md": "Ok"},
    )
    first_id = first.json()["id"]
    second = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "Now love it"},
    )
    second_id = second.json()["id"]
    assert first_id == second_id
    assert second.json()["stars"] == 5
    assert second.json()["body_md"] == "Now love it"

    factory = app.state.session_factory
    with factory() as session:
        count = session.execute(select(DataProductReview)).all()
        assert len(count) == 1


@pytest.mark.asyncio
async def test_put_rejects_out_of_range_stars(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``stars`` outside 1..5 returns 400 at the API layer."""
    _seed_product(tmp_path)
    for bad in (0, 6, -1, 99):
        res = await admin_client.put(
            "/api/data-products/main/sales_gold/reviews",
            json={"stars": bad, "body_md": ""},
        )
        assert res.status_code == 400, f"stars={bad} should 400"


@pytest.mark.asyncio
async def test_put_requires_stars(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Missing ``stars`` returns 400."""
    _seed_product(tmp_path)
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"body_md": "I forgot"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_own_review(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """DELETE removes the caller's review; subsequent PUT creates a new one."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 4, "body_md": "x"},
    )
    res = await admin_client.delete("/api/data-products/main/sales_gold/reviews")
    assert res.status_code == 200
    assert res.json() == {"deleted": True}
    # idempotent re-delete
    again = await admin_client.delete("/api/data-products/main/sales_gold/reviews")
    assert again.json() == {"deleted": False}
    # PUT after DELETE creates fresh
    put = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 2, "body_md": ""},
    )
    assert put.status_code == 200
    assert put.json()["stars"] == 2


# ---------------------------------------------------------------------------
# List + summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_summary_and_my_review(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """``my_review`` shows the caller's row + summary averages all rows."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "by admin"},
    )
    await non_admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 1, "body_md": "by nonadmin"},
    )
    body = (
        await admin_client.get("/api/data-products/main/sales_gold/reviews")
    ).json()
    assert body["summary"]["count"] == 2
    assert body["summary"]["avg_stars"] == 3.0
    assert body["my_review"]["stars"] == 5


@pytest.mark.asyncio
async def test_list_summary_empty(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """No reviews → ``count=0``, ``avg_stars=null``, ``my_review=null``."""
    _seed_product(tmp_path)
    body = (
        await admin_client.get("/api/data-products/main/sales_gold/reviews")
    ).json()
    assert body["summary"] == {"avg_stars": None, "count": 0}
    assert body["my_review"] is None
    assert body["reviews"] == []


# ---------------------------------------------------------------------------
# Browse-page enrichment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_listing_includes_review_aggregate(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/data-products`` carries avg_stars + review_count per row."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 4, "body_md": ""},
    )
    body = (await admin_client.get("/api/data-products")).json()
    product = body["data_products"][0]
    assert product["avg_stars"] == 4.0
    assert product["review_count"] == 1


@pytest.mark.asyncio
async def test_browse_listing_no_reviews_means_zero(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Products with no reviews get ``avg_stars=None, review_count=0``."""
    _seed_product(tmp_path)
    body = (await admin_client.get("/api/data-products")).json()
    product = body["data_products"][0]
    assert product["avg_stars"] is None
    assert product["review_count"] == 0


# ---------------------------------------------------------------------------
# Cross-workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_workspace_isolated(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A review in workspace 1 is invisible from workspace 2."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "ws1"},
    )

    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=2,
                slug="second",
                name="Second",
                description="iso test",
                created_at=now,
            )
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        session.add(
            WorkspaceMember(
                workspace_id=2,
                user_id=nonadmin.id,
                role="member",
                created_at=now,
            )
        )
        nonadmin.default_workspace_id = 2
        session.add(nonadmin)
        session.commit()

    res = await non_admin_client.get(
        "/api/data-products/main/sales_gold/reviews",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404
