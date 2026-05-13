"""Phase 76.2 — user profiles, follows, badges.

Coverage:

* ``GET /api/users/{id}/profile`` returns defaults for users with
  no UserProfile row + reflects PUT-updates.
* ``PUT /api/users/{id}/profile`` is owner-or-admin gated.
* Self-follow is rejected; follow + unfollow are idempotent;
  follower listing matches.
* :func:`award_badges` synthetic-seed: steward of 3 DPs ⇒
  ``steward_3plus``; idempotent on repeat invocation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._user_badge import UserBadge
from pointlessql.models.social._user_follow import UserFollow
from pointlessql.services.social.badges import award_badges


def _yaml(catalog: str, schema: str, steward: str = "alice@example.com") -> str:
    """Minimal contract YAML for a one-table data product."""
    return f"""\
data_product:
  name: {schema}
  version: "1.0.0"
  description: synthetic
  catalog: {catalog}
  schema: {schema}
  steward_email: {steward}
  sla_minutes: 60
  tables:
    - name: t
      primary_key: [id]
      columns:
        - {{name: id, type: long, nullable: false}}
"""


@pytest.fixture
async def anonymous_client() -> AsyncIterator[httpx.AsyncClient]:
    """``httpx.AsyncClient`` with no auth cookie."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Profile GET + PUT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_get_defaults_for_user_without_row(
    admin_client: httpx.AsyncClient,
) -> None:
    """GET on a user with no UserProfile row returns the default shape."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    res = await admin_client.get(f"/api/users/{admin_id}/profile")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile"]["bio_md"] == ""
    assert body["counts"]["followers"] == 0
    assert body["badges"] == []


@pytest.mark.asyncio
async def test_profile_put_updates_bio_owner(
    admin_client: httpx.AsyncClient,
) -> None:
    """Owner-PUT persists bio + location."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    res = await admin_client.put(
        f"/api/users/{admin_id}/profile",
        json={"bio_md": "I steward stuff.", "location": "Berlin"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["bio_md"] == "I steward stuff."
    assert res.json()["location"] == "Berlin"


@pytest.mark.asyncio
async def test_profile_put_non_owner_rejected(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-admin cannot edit someone else's profile."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    res = await non_admin_client.put(
        f"/api/users/{admin_id}/profile",
        json={"bio_md": "hacked"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_profile_put_admin_can_edit_other(
    admin_client: httpx.AsyncClient,
) -> None:
    """Admin can edit another user's profile."""
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        nonadmin_id = nonadmin.id
    res = await admin_client.put(
        f"/api/users/{nonadmin_id}/profile",
        json={"bio_md": "set by admin"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["bio_md"] == "set by admin"


# ---------------------------------------------------------------------------
# User-to-user follows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_follow_rejected(admin_client: httpx.AsyncClient) -> None:
    """Following yourself returns 400."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    res = await admin_client.post(f"/api/users/{admin_id}/follow")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_follow_idempotent_then_unfollow(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST is idempotent, DELETE round-trips cleanly."""
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        nonadmin_id = nonadmin.id

    first = await admin_client.post(f"/api/users/{nonadmin_id}/follow")
    assert first.status_code == 200
    assert first.json()["added"] is True
    second = await admin_client.post(f"/api/users/{nonadmin_id}/follow")
    assert second.status_code == 200
    assert second.json()["added"] is False

    with factory() as session:
        rows = (
            session.execute(
                select(UserFollow).where(
                    UserFollow.followed_user_id == nonadmin_id
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1

    removed = await admin_client.delete(f"/api/users/{nonadmin_id}/follow")
    assert removed.status_code == 200
    assert removed.json()["removed"] is True
    removed_again = await admin_client.delete(f"/api/users/{nonadmin_id}/follow")
    assert removed_again.status_code == 200
    assert removed_again.json()["removed"] is False


@pytest.mark.asyncio
async def test_follow_lists(admin_client: httpx.AsyncClient) -> None:
    """Followers + Following endpoints return matched users."""
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        nonadmin_id = nonadmin.id
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    await admin_client.post(f"/api/users/{nonadmin_id}/follow")
    followers = await admin_client.get(f"/api/users/{nonadmin_id}/followers")
    assert followers.status_code == 200
    assert any(f["user_id"] == admin_id for f in followers.json()["followers"])
    following = await admin_client.get(f"/api/users/{admin_id}/following")
    assert following.status_code == 200
    assert any(
        f["user_id"] == nonadmin_id for f in following.json()["following"]
    )


# ---------------------------------------------------------------------------
# Badge loop
# ---------------------------------------------------------------------------


def _seed_steward_dps(tmp_path: Path, count: int, steward_id: int) -> None:
    """Seed *count* data products all stewarded by *steward_id*."""
    factory = app.state.session_factory
    for idx in range(count):
        path = tmp_path / f"dp_{idx}.yaml"
        path.write_text(_yaml("main", f"sch_{idx}"), encoding="utf-8")
        load_contract(path, factory=factory)
    # The yaml loader assigns steward_user_id by email-lookup; for
    # tests we just patch them all to the target id directly.
    with factory() as session:
        for dp in session.execute(select(DataProduct)).scalars().all():
            dp.steward_user_id = steward_id
        session.commit()


@pytest.mark.asyncio
async def test_award_badges_steward_threshold(tmp_path: Path) -> None:
    """Stewarding 3 DPs awards the ``steward_3plus`` badge."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id

    _seed_steward_dps(tmp_path, 3, admin_id)
    inserted = await __import__("asyncio").to_thread(award_badges, factory)
    assert inserted >= 1

    with factory() as session:
        badges = (
            session.execute(
                select(UserBadge).where(UserBadge.user_id == admin_id)
            )
            .scalars()
            .all()
        )
    assert any(b.badge_key == "steward_3plus" for b in badges)


@pytest.mark.asyncio
async def test_award_badges_idempotent(tmp_path: Path) -> None:
    """A second run does not duplicate a sticky badge."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    _seed_steward_dps(tmp_path, 3, admin_id)

    import asyncio as _aio

    first = await _aio.to_thread(award_badges, factory)
    second = await _aio.to_thread(award_badges, factory)
    assert first >= 1
    assert second == 0


@pytest.mark.asyncio
async def test_award_badges_below_threshold_noop(tmp_path: Path) -> None:
    """Stewarding only 2 DPs does not award the ``steward_3plus`` badge."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    _seed_steward_dps(tmp_path, 2, admin_id)

    import asyncio as _aio

    await _aio.to_thread(award_badges, factory)
    with factory() as session:
        badges = (
            session.execute(
                select(UserBadge).where(UserBadge.user_id == admin_id)
            )
            .scalars()
            .all()
        )
    assert not any(b.badge_key == "steward_3plus" for b in badges)


# ---------------------------------------------------------------------------
# HTML profile route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_html_page_renders(admin_client: httpx.AsyncClient) -> None:
    """``GET /users/{id}`` returns 200 + the user's display_name in the body."""
    factory = app.state.session_factory
    with factory() as session:
        admin = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        admin_id = admin.id
    res = await admin_client.get(f"/users/{admin_id}")
    assert res.status_code == 200
    assert "Test User" in res.text


@pytest.mark.asyncio
async def test_profile_html_anonymous_redirects(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous visitor → 303 to login."""
    res = await anonymous_client.get("/users/1")
    assert res.status_code in (302, 303, 401, 403)
