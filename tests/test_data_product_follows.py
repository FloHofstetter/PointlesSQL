"""Tests for the data-product follow / subscribe surface.

Covers POST/DELETE idempotency, the public count vs steward-only
full-list privacy gate, the /data-products/followed HTML index,
and cross-workspace isolation.
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
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_follow import SocialFollow
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
# Follow / unfollow idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_creates_row(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """POST /follow inserts one row + flips ``following=True``."""
    _seed_product(tmp_path)
    res = await admin_client.post("/api/data-products/main/sales_gold/follow")
    assert res.status_code == 200
    body = res.json()
    assert body["followed"] is True
    assert body["already"] is False

    count = (await admin_client.get("/api/data-products/main/sales_gold/followers/count")).json()
    assert count == {"count": 1, "following": True}


@pytest.mark.asyncio
async def test_follow_is_idempotent(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Second POST returns ``already=True`` without a duplicate row."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    res = await admin_client.post("/api/data-products/main/sales_gold/follow")
    assert res.json()["already"] is True
    factory = app.state.session_factory
    with factory() as session:
        assert len(session.execute(select(SocialFollow)).all()) == 1


@pytest.mark.asyncio
async def test_unfollow_round_trip(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """DELETE drops the row + second DELETE returns removed=False."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    first = await admin_client.delete("/api/data-products/main/sales_gold/follow")
    assert first.json() == {"followed": False, "removed": True}
    second = await admin_client.delete("/api/data-products/main/sales_gold/follow")
    assert second.json() == {"followed": False, "removed": False}


# ---------------------------------------------------------------------------
# Privacy: full list vs count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_endpoint_is_per_user(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """The ``count`` endpoint exposes total + caller's own follow state."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    res = (await non_admin_client.get("/api/data-products/main/sales_gold/followers/count")).json()
    assert res == {"count": 1, "following": False}


@pytest.mark.asyncio
async def test_followers_full_list_requires_steward_or_admin(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-steward non-admin gets 403 on the full followers list."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    res = await non_admin_client.get("/api/data-products/main/sales_gold/followers")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_followers_full_list_admin_passes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Install-admin sees the full followers list."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    res = await admin_client.get("/api/data-products/main/sales_gold/followers")
    assert res.status_code == 200
    body = res.json()
    assert len(body["followers"]) == 1
    assert body["followers"][0]["email"] == "test@test.com"


@pytest.mark.asyncio
async def test_followers_full_list_steward_passes(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """When the caller is the product's steward, they see the full list."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        dp = session.execute(select(DataProduct)).scalar_one()
        dp.steward_user_id = nonadmin.id
        session.add(dp)
        session.commit()

    res = await non_admin_client.get("/api/data-products/main/sales_gold/followers")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# /data-products/followed HTML page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_followed_page_lists_only_callers_follows(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """The HTML index lists only the calling user's followed DPs."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")
    # non-admin has nothing followed
    page = await non_admin_client.get("/data-products/followed")
    assert page.status_code == 200
    assert "pql-no-follows-empty" in page.text
    # admin has the seeded follow
    admin_page = await admin_client.get("/data-products/followed")
    assert admin_page.status_code == 200
    assert "main.sales_gold" in admin_page.text


# ---------------------------------------------------------------------------
# Cross-workspace isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_cross_workspace_isolated(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Following in workspace 1 doesn't expose the row in workspace 2."""
    _seed_product(tmp_path)
    await admin_client.post("/api/data-products/main/sales_gold/follow")

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
        "/api/data-products/main/sales_gold/followers/count",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404
