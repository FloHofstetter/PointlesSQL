"""topics taxonomy, DP assignment, topic-follows.

Coverage:

* Topic CRUD via the JSON API.
* Steward-only DP↔topic assignment with replace-all semantics.
* Idempotent topic-follow / unfollow.
* ``pointlessql.topic.dp_added`` inbox fan-out to topic followers.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._topic import (
    DataProductTopic,
    UserTopicFollow,
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


def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + load it; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# Topic CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topic_create_admin(admin_client: httpx.AsyncClient) -> None:
    """Admin can create a topic; slug auto-derived from display name."""
    res = await admin_client.post("/api/topics", json={"display_name": "Finance"})
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == "finance"
    assert res.json()["dp_count"] == 0


@pytest.mark.asyncio
async def test_topic_create_collision_appends_suffix(
    admin_client: httpx.AsyncClient,
) -> None:
    """Re-creating with the same name yields a -2 suffix on slug."""
    first = await admin_client.post("/api/topics", json={"display_name": "Finance"})
    second = await admin_client.post("/api/topics", json={"display_name": "Finance"})
    assert first.json()["slug"] == "finance"
    assert second.json()["slug"] == "finance-2"


@pytest.mark.asyncio
async def test_topic_create_non_admin_rejected(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A plain member cannot create a topic."""
    res = await non_admin_client.post("/api/topics", json={"display_name": "Spam"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_topic_create_rejects_empty_name(
    admin_client: httpx.AsyncClient,
) -> None:
    """Empty display name returns 400."""
    res = await admin_client.post("/api/topics", json={"display_name": "  "})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# DP↔topic assignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_dp_topics_steward_only(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-admin / non-steward gets 403 on topic assignment."""
    _seed_product(tmp_path)
    await admin_client.post("/api/topics", json={"display_name": "Gold"})
    res = await non_admin_client.put(
        "/api/data-products/main/sales_gold/topics",
        json={"topics": ["gold"]},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_set_dp_topics_replaces_existing(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """PUT replaces the DP's full topic set (not additive)."""
    _seed_product(tmp_path)
    await admin_client.post("/api/topics", json={"display_name": "Gold"})
    await admin_client.post("/api/topics", json={"display_name": "Finance"})
    first = await admin_client.put(
        "/api/data-products/main/sales_gold/topics",
        json={"topics": ["gold", "finance"]},
    )
    assert first.status_code == 200
    assert set(first.json()["topic_slugs"]) == {"gold", "finance"}

    second = await admin_client.put(
        "/api/data-products/main/sales_gold/topics",
        json={"topics": ["finance"]},
    )
    assert second.status_code == 200
    assert second.json()["topic_slugs"] == ["finance"]

    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(DataProductTopic)).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_set_dp_topics_unknown_slug_400(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An unknown slug in the topics list returns 400."""
    _seed_product(tmp_path)
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/topics",
        json={"topics": ["nope"]},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Topic-follow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follow_topic_idempotent(admin_client: httpx.AsyncClient) -> None:
    """POST is idempotent; DELETE round-trips."""
    create = await admin_client.post("/api/topics", json={"display_name": "Lakehouse"})
    slug = create.json()["slug"]
    first = await admin_client.post(f"/api/topics/{slug}/follow")
    second = await admin_client.post(f"/api/topics/{slug}/follow")
    assert first.json()["added"] is True
    assert second.json()["added"] is False

    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(UserTopicFollow)).scalars().all()
    assert len(rows) == 1

    removed = await admin_client.delete(f"/api/topics/{slug}/follow")
    assert removed.json()["removed"] is True


@pytest.mark.asyncio
async def test_follow_unknown_topic_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Follow on a missing slug returns 404."""
    res = await admin_client.post("/api/topics/nope/follow")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Fan-out on DP-joined-topic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topic_dp_added_fans_out_to_followers(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Adding a DP to a topic notifies the topic's followers."""
    _seed_product(tmp_path)
    create = await admin_client.post("/api/topics", json={"display_name": "Gold"})
    slug = create.json()["slug"]
    # Non-admin follows the topic.
    await non_admin_client.post(f"/api/topics/{slug}/follow")

    # Admin assigns the DP to the topic.
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/topics",
        json={"topics": [slug]},
    )
    assert res.status_code == 200

    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        recipients = (
            session.execute(
                select(UserNotification.recipient_user_id).where(
                    UserNotification.event_type == "pointlessql.topic.dp_added"
                )
            )
            .scalars()
            .all()
        )
    assert nonadmin.id in recipients


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topics_index_html_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/topics`` returns 200."""
    res = await admin_client.get("/topics")
    assert res.status_code == 200
    assert "Topics" in res.text


@pytest.mark.asyncio
async def test_topic_detail_html_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/topics/{slug}`` returns 200 with the topic name."""
    await admin_client.post("/api/topics", json={"display_name": "Finance"})
    res = await admin_client.get("/topics/finance")
    assert res.status_code == 200
    assert "Finance" in res.text


@pytest.mark.asyncio
async def test_topic_detail_html_missing_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown topic slug returns 404 from the HTML route."""
    res = await admin_client.get("/topics/nope")
    assert res.status_code == 404
