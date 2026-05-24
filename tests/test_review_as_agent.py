"""``?as_agent=`` on reviews PUT.

Coverage:

* Principal can author a review under the agent identity.  The
  row carries both ``author_user_id`` (principal) and
  ``author_agent_id``.
* Non-principal gets 403.
* Unknown slug returns 404.
* GET surfaces the agent payload in the listing.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: test@test.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> int:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _admin_user_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(select(User.id).where(User.email == "test@test.com")).scalar_one()
        )


@pytest.mark.asyncio
async def test_review_as_agent_principal_ok(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Principal authors a review under the agent identity."""
    dp_id = _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Reviewer Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]

    res = await admin_client.put(
        f"/api/data-products/main/sales_gold/reviews?as_agent={slug}",
        json={"stars": 4, "body_md": "robotic praise"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["agent"] is not None
    assert payload["agent"]["slug"] == slug
    assert payload["author"]["user_id"] == principal_id

    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReview).where(
                DataProductReview.data_product_id == dp_id,
                DataProductReview.author_user_id == principal_id,
            )
        ).scalar_one()
        assert row.author_agent_id is not None


@pytest.mark.asyncio
async def test_review_as_agent_non_principal_rejected(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-principal cannot speak as someone else's agent."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Owners Reviewer",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    res = await non_admin_client.put(
        f"/api/data-products/main/sales_gold/reviews?as_agent={slug}",
        json={"stars": 5, "body_md": "stolen review"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_review_as_unknown_agent_404(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Unknown ``?as_agent=`` slug returns 404."""
    _seed_product(tmp_path)
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews?as_agent=phantom",
        json={"stars": 4},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_review_listing_includes_agent_payload(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The agent payload surfaces in the review listing."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Visible Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    await admin_client.put(
        f"/api/data-products/main/sales_gold/reviews?as_agent={slug}",
        json={"stars": 3},
    )
    listing = await admin_client.get("/api/data-products/main/sales_gold/reviews")
    body = listing.json()
    agent_rows = [r for r in body["reviews"] if r.get("agent")]
    assert agent_rows
    assert agent_rows[0]["agent"]["slug"] == slug


@pytest.mark.asyncio
async def test_review_upsert_clears_agent_when_direct(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A follow-up direct PUT clears the agent badge.

    Phase-76.5.1 semantics: ``author_agent_id`` mirrors the most
    recent PUT, so a steward who first posts ``?as_agent=`` then
    fixes a typo directly should not keep the agent badge.
    """
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={"display_name": "Toggle Bot", "principal_user_id": principal_id},
    )
    slug = create.json()["slug"]
    await admin_client.put(
        f"/api/data-products/main/sales_gold/reviews?as_agent={slug}",
        json={"stars": 4},
    )
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "typo fix"},
    )
    assert res.status_code == 200
    assert res.json()["agent"] is None
