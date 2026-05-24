"""per-user feed + notification preferences.

Coverage:

* ``GET /api/feed`` surfaces inbox rows + followed-users overlay.
* Filters: ``mentions`` / ``my`` / ``followed_users``.
* ``GET /api/settings/notifications`` fills missing event types
  with all-true defaults; PUT merge-updates persist.
* Fanout respects per-user opt-out — a recipient with the event
  type's ``inbox`` flag set to ``false`` receives no row.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications.fanout import fanout_event

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
# Feed endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_returns_inbox_rows(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """An inbox row created via fan-out surfaces in the recipient's feed."""
    _seed_product(tmp_path)
    # Non-admin follows the DP so the admin's comment triggers a
    # fan-out row in non-admin's inbox.
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "Hi from admin"},
    )

    res = await non_admin_client.get("/api/feed", params={"filter": "all"})
    assert res.status_code == 200
    body = res.json()
    assert any(r["event_type"] == "pointlessql.data_product.commented" for r in body["rows"])


@pytest.mark.asyncio
async def test_feed_filter_my_only_authored(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``filter=my`` returns rows whose actor is the caller."""
    _seed_product(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "self-authored"},
    )
    res = await admin_client.get("/api/feed", params={"filter": "my"})
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert all(r["kind"] in ("comment", "review") for r in rows)
    assert any("self-authored" in r["summary_md"] for r in rows)


@pytest.mark.asyncio
async def test_feed_filter_mentions(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """``filter=mentions`` shows comments where the caller is mentioned."""
    _seed_product(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "@nonadmin@test.com pls review"},
    )
    res = await non_admin_client.get("/api/feed", params={"filter": "mentions"})
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert any("pls review" in r["summary_md"] for r in rows)


@pytest.mark.asyncio
async def test_feed_search_substring(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """The ``q`` query param filters on case-insensitive substring."""
    _seed_product(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "matches-this"},
    )
    res = await admin_client.get("/api/feed", params={"filter": "my", "q": "MATCHES"})
    assert res.status_code == 200
    rows = res.json()["rows"]
    assert any("matches-this" in r["summary_md"] for r in rows)


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_prefs_defaults_all_true(
    admin_client: httpx.AsyncClient,
) -> None:
    """Empty stored prefs render as all-true for every known event."""
    res = await admin_client.get("/api/settings/notifications")
    assert res.status_code == 200
    body = res.json()
    assert body["known_event_types"]
    for event_type in body["known_event_types"]:
        per = body["prefs"][event_type]
        assert per["inbox"] is True
        assert per["email"] is True
        assert per["webhook"] is True


@pytest.mark.asyncio
async def test_put_prefs_merge_update(admin_client: httpx.AsyncClient) -> None:
    """Setting one channel false on one event leaves the rest unchanged."""
    target = "pointlessql.data_product.commented"
    res = await admin_client.put(
        "/api/settings/notifications",
        json={target: {"inbox": False}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["prefs"][target]["inbox"] is False
    assert body["prefs"][target]["email"] is True


@pytest.mark.asyncio
async def test_fanout_respects_inbox_optout(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A follower with inbox=False on the event type receives no row."""
    dp_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(select(User).where(User.email == "test@test.com")).scalar_one()
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        admin_id = admin.id
        nonadmin_id = nonadmin.id
        admin.notification_prefs_json = json.dumps(
            {"pointlessql.data_product.commented": {"inbox": False}}
        )
        session.commit()

    inserted = fanout_event(
        factory,
        event_type="pointlessql.data_product.commented",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=nonadmin_id,
        source_url="/test",
        summary_md="test",
        data_product_id=dp_id,
        extra_recipients=[admin_id],
    )
    # Admin opted out, so the only recipient eligibility drops to
    # zero — no row was inserted.
    assert inserted == 0

    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.recipient_user_id == admin_id,
                    UserNotification.event_type == "pointlessql.data_product.commented",
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


@pytest.mark.asyncio
async def test_feed_html_renders(admin_client: httpx.AsyncClient) -> None:
    """``/feed`` returns 200 + the page title fragment."""
    res = await admin_client.get("/feed")
    assert res.status_code == 200
    assert "Feed" in res.text


@pytest.mark.asyncio
async def test_settings_notifications_html_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/settings/notifications`` returns 200."""
    res = await admin_client.get("/settings/notifications")
    assert res.status_code == 200
    assert "Notification preferences" in res.text
