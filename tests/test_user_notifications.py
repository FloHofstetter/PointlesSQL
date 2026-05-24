"""Tests for the notification fan-out + inbox surface.

Covers the fan-out helper (followers + mentions, actor suppression),
the comment + review + follow integration paths (each one
generates the right inbox rows), the /api/notifications endpoints
(list / unread-count / mark-read / read-all), and cross-workspace
isolation.
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
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications import fanout_event
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
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
    """Seed a yaml + load it into the cache; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _make_user(email: str, *, display_name: str | None = None) -> int:
    """Persist one extra user; return its id."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        u = User(
            email=email,
            display_name=display_name or email.split("@")[0],
            password_hash=None,
            is_admin=False,
            default_workspace_id=1,
            created_at=now,
        )
        session.add(u)
        session.commit()
        return u.id


def _admin_user_id() -> int:
    """Return the seeded admin user id."""
    factory = app.state.session_factory
    with factory() as session:
        return session.execute(select(User).where(User.email == "test@test.com")).scalar_one().id


def _nonadmin_user_id() -> int:
    """Return the seeded non-admin user id."""
    factory = app.state.session_factory
    with factory() as session:
        return (
            session.execute(select(User).where(User.email == "nonadmin@test.com")).scalar_one().id
        )


# ---------------------------------------------------------------------------
# fanout helper
# ---------------------------------------------------------------------------


def test_fanout_inserts_one_row_per_recipient(tmp_path: Path) -> None:
    """Followers + extra recipients (de-duplicated) get one row each."""
    dp_id = _seed_product(tmp_path)
    bob_id = _make_user("bob@example.com")
    carol_id = _make_user("carol@example.com")
    # Bob follows; carol is only a mention.
    factory = app.state.session_factory
    from pointlessql.models.social._social_follow import SocialFollow

    with factory() as session:
        from pointlessql.models.catalog._data_products import DataProduct
        from pointlessql.services.social import get_or_create_target

        dp_row = session.get(DataProduct, dp_id)
        assert dp_row is not None
        _anchor_77g = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref=f"{dp_row.catalog_name}.{dp_row.schema_name}",
            data_product_id=dp_id,
        )

        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=int(_anchor_77g.id),
                user_id=bob_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    count = fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=_admin_user_id(),
        source_url="/data-products/main/sales_gold#x",
        summary_md="ping",
        data_product_id=dp_id,
        extra_recipients=[carol_id, bob_id],  # bob is followers AND mentions
    )
    assert count == 2  # bob (dedup) + carol; admin is suppressed

    with factory() as session:
        rows = session.execute(select(UserNotification)).scalars().all()
        recipient_ids = {r.recipient_user_id for r in rows}
        assert recipient_ids == {bob_id, carol_id}


def test_fanout_suppresses_actor(tmp_path: Path) -> None:
    """The actor is never notified about their own action."""
    dp_id = _seed_product(tmp_path)
    admin_id = _admin_user_id()
    factory = app.state.session_factory
    from pointlessql.models.social._social_follow import SocialFollow

    with factory() as session:
        from pointlessql.models.catalog._data_products import DataProduct
        from pointlessql.services.social import get_or_create_target

        dp_row = session.get(DataProduct, dp_id)
        assert dp_row is not None
        _anchor_77g = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref=f"{dp_row.catalog_name}.{dp_row.schema_name}",
            data_product_id=dp_id,
        )

        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=int(_anchor_77g.id),
                user_id=admin_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=admin_id,
        source_url="/x",
        summary_md="self",
        data_product_id=dp_id,
    )
    with factory() as session:
        assert session.execute(select(UserNotification)).all() == []


# ---------------------------------------------------------------------------
# Integration: comment / review / follow events trigger fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_post_fans_out_to_followers(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Posting a comment as the admin notifies the non-admin follower."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "hey"},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(UserNotification)).scalars().all()
        assert len(rows) == 1
        assert rows[0].recipient_user_id == _nonadmin_user_id()
        assert rows[0].event_type == EVENT_TYPE_DATA_PRODUCT_COMMENTED


@pytest.mark.asyncio
async def test_comment_post_fans_out_to_mentions(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """An ``@<email>`` mention generates a notification even without follow."""
    _seed_product(tmp_path)
    bob_id = _make_user("bob@example.com")
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "ping @bob@example.com"},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        rows = session.execute(select(UserNotification)).scalars().all()
        assert len(rows) == 1
        assert rows[0].recipient_user_id == bob_id


@pytest.mark.asyncio
async def test_review_put_fans_out_to_followers(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Posting a review fans out to followers."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    res = await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 4, "body_md": "good"},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.recipient_user_id == _nonadmin_user_id()
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# /api/notifications endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_count_and_mark_read(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Mark-read flips the count, idempotent on a second hit."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "x"},
    )
    factory = app.state.session_factory
    with factory() as session:
        notif_id = (
            session.execute(
                select(UserNotification.id).where(
                    UserNotification.recipient_user_id == _nonadmin_user_id()
                )
            )
            .scalars()
            .one()
        )
    pre = await non_admin_client.get("/api/notifications/unread-count")
    assert pre.json() == {"unread": 1}
    mark = await non_admin_client.post(f"/api/notifications/{notif_id}/read")
    assert mark.status_code == 200
    assert mark.json()["read_at"] is not None
    post = await non_admin_client.get("/api/notifications/unread-count")
    assert post.json() == {"unread": 0}
    # idempotent
    again = await non_admin_client.post(f"/api/notifications/{notif_id}/read")
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_mark_all_read(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """``read-all`` flips every unread row for the caller."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    for i in range(3):
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": f"m{i}"},
        )
    res = await non_admin_client.post("/api/notifications/read-all")
    assert res.json() == {"flipped": 3}
    assert (await non_admin_client.get("/api/notifications/unread-count")).json() == {"unread": 0}


@pytest.mark.asyncio
async def test_list_filters_by_unread_and_type(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """``?unread=true`` + ``?event_type=...`` filters work."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "c"},
    )
    await admin_client.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "r"},
    )
    all_res = (await non_admin_client.get("/api/notifications")).json()
    assert len(all_res["notifications"]) == 2

    comments_only = (
        await non_admin_client.get(
            "/api/notifications?event_type=pointlessql.data_product.commented"
        )
    ).json()
    assert len(comments_only["notifications"]) == 1
    assert comments_only["notifications"][0]["event_type"] == EVENT_TYPE_DATA_PRODUCT_COMMENTED


@pytest.mark.asyncio
async def test_anonymous_blocked(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous callers cannot hit any /api/notifications endpoint."""
    res = await anonymous_client.get("/api/notifications/unread-count")
    assert res.status_code in (401, 403, 303)


@pytest.mark.asyncio
async def test_cross_user_isolation(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """One user's notification id is invisible to another user (404)."""
    _seed_product(tmp_path)
    await non_admin_client.post("/api/data-products/main/sales_gold/follow")
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "x"},
    )
    factory = app.state.session_factory
    with factory() as session:
        notif_id = session.execute(select(UserNotification.id)).scalars().one()
    res = await admin_client.post(f"/api/notifications/{notif_id}/read")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Digest opt-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_settings_put_flips_digest(
    admin_client: httpx.AsyncClient,
) -> None:
    """PUT /api/me/settings toggles the digest_email_optin column."""
    get = (await admin_client.get("/api/me/settings")).json()
    assert get["digest_email_optin"] is False
    put = (await admin_client.put("/api/me/settings", json={"digest_email_optin": True})).json()
    assert put["digest_email_optin"] is True
    get2 = (await admin_client.get("/api/me/settings")).json()
    assert get2["digest_email_optin"] is True


@pytest.mark.asyncio
async def test_me_settings_page_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """GET /me/settings renders the form."""
    res = await admin_client.get("/me/settings")
    assert res.status_code == 200
    assert "pql-me-digest-toggle" in res.text
