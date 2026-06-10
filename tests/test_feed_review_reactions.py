"""Tests for per-review emoji reactions.

Reviews of one product share that product's social anchor, so review
reactions key on the review PK.  These tests cover the add / list /
remove round-trip, idempotency, emoji validation, and — the reason the
per-review key exists — that reacting to one review does not move a
sibling review's counts.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_product_reviews import DataProductReview
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

REACT_BASE = "/api/social/dp/main.sales_gold/reviews"


def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + load it into the cache; return the data_products id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _review_ids() -> list[int]:
    """Return all review ids for the seeded product, oldest first."""
    factory = app.state.session_factory
    with factory() as session:
        return [
            int(r.id)
            for r in session.execute(
                select(DataProductReview).order_by(DataProductReview.id)
            ).scalars()
        ]


@pytest.mark.asyncio
async def test_react_to_review_round_trip(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """POST adds a reaction; GET reflects it; DELETE removes it."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "Excellent product."},
    )
    review_id = _review_ids()[0]

    add = await admin_client.post(f"{REACT_BASE}/{review_id}/reactions", json={"emoji": "👍"})
    assert add.status_code == 200, add.text
    assert add.json() == {"review_id": review_id, "emoji": "👍", "added": True}

    got = await admin_client.get(f"{REACT_BASE}/{review_id}/reactions")
    assert got.status_code == 200, got.text
    by_emoji = {r["emoji"]: r for r in got.json()["reactions"]}
    assert by_emoji["👍"]["count"] == 1
    assert by_emoji["👍"]["has_current_user_reacted"] is True
    assert by_emoji["❤️"]["count"] == 0

    rm = await admin_client.delete(f"{REACT_BASE}/{review_id}/reactions/👍")
    assert rm.status_code == 200, rm.text
    assert rm.json()["removed"] is True

    after = await admin_client.get(f"{REACT_BASE}/{review_id}/reactions")
    assert {r["emoji"]: r["count"] for r in after.json()["reactions"]}["👍"] == 0


@pytest.mark.asyncio
async def test_review_reaction_is_idempotent(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Re-applying the same (review, user, emoji) triple is a no-op."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 4, "body_md": "Solid."},
    )
    review_id = _review_ids()[0]

    first = await admin_client.post(f"{REACT_BASE}/{review_id}/reactions", json={"emoji": "🎉"})
    second = await admin_client.post(f"{REACT_BASE}/{review_id}/reactions", json={"emoji": "🎉"})
    assert first.json()["added"] is True
    assert second.json()["added"] is False

    got = await admin_client.get(f"{REACT_BASE}/{review_id}/reactions")
    assert {r["emoji"]: r["count"] for r in got.json()["reactions"]}["🎉"] == 1


@pytest.mark.asyncio
async def test_review_reaction_rejects_unknown_emoji(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An emoji outside the canonical set is a 400."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 3, "body_md": "Okay."},
    )
    review_id = _review_ids()[0]
    res = await admin_client.post(f"{REACT_BASE}/{review_id}/reactions", json={"emoji": "🚀"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_sibling_reviews_have_independent_counts(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Reacting to one review must not move a sibling review's count.

    This is the whole reason review reactions key on the review PK
    rather than the shared product anchor.
    """
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "From the admin."},
    )
    await non_admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 2, "body_md": "From the other user."},
    )
    ids = _review_ids()
    assert len(ids) == 2, "expected one review per author"
    review_a, review_b = ids

    add = await admin_client.post(f"{REACT_BASE}/{review_a}/reactions", json={"emoji": "❤️"})
    assert add.json()["added"] is True

    got_a = await admin_client.get(f"{REACT_BASE}/{review_a}/reactions")
    got_b = await admin_client.get(f"{REACT_BASE}/{review_b}/reactions")
    counts_a = {r["emoji"]: r["count"] for r in got_a.json()["reactions"]}
    counts_b = {r["emoji"]: r["count"] for r in got_b.json()["reactions"]}
    assert counts_a["❤️"] == 1
    assert counts_b["❤️"] == 0, "sibling review's count must stay independent"


@pytest.mark.asyncio
async def test_review_reactions_with_names(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """``?with_names=1`` enriches each emoji with its reactor identities."""
    _seed_product(tmp_path)
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "Top tier."},
    )
    review_id = _review_ids()[0]
    await admin_client.post(f"{REACT_BASE}/{review_id}/reactions", json={"emoji": "👍"})

    plain = await admin_client.get(f"{REACT_BASE}/{review_id}/reactions")
    assert "users" not in plain.json()["reactions"][0]

    named = await admin_client.get(f"{REACT_BASE}/{review_id}/reactions?with_names=1")
    by_emoji = {r["emoji"]: r for r in named.json()["reactions"]}
    thumb = by_emoji["👍"]
    assert thumb["count"] == 1
    assert thumb["users"] and thumb["users"][0]["display_name"]
    assert "id" in thumb["users"][0]


@pytest.mark.asyncio
async def test_react_to_missing_review_is_404(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A reaction on a non-existent review id is a clean 404."""
    _seed_product(tmp_path)
    res = await admin_client.post(f"{REACT_BASE}/999999/reactions", json={"emoji": "👍"})
    assert res.status_code == 404
