"""Tests for the Phase-12 saved-queries service + API."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.services import saved_queries as sq




def _admin_id() -> int:
    return 1  # conftest.py registers admin first → id=1


def _non_admin_id() -> int:
    return 2  # second registered user → id=2


# -- service-level -------------------------------------------------


def test_make_slug_is_url_safe_and_unique() -> None:
    s1 = sq.make_slug("Daily orders report!")
    s2 = sq.make_slug("Daily orders report!")
    # sanitised: lowercase, hyphens, no punctuation.
    assert s1.startswith("daily-orders-report-")
    # random suffix → different slugs for identical titles.
    assert s1 != s2


def test_make_slug_falls_back_on_empty_title() -> None:
    s = sq.make_slug("")
    assert s.startswith("query-")


def test_create_validates_title_and_sql() -> None:
    factory = app.state.session_factory
    with pytest.raises(ValidationError, match="Title"):
        sq.create_saved_query(
            factory, owner_id=_admin_id(), title="", description=None, sql_text="SELECT 1"
        )
    with pytest.raises(ValidationError, match="SQL"):
        sq.create_saved_query(
            factory, owner_id=_admin_id(), title="x", description=None, sql_text=""
        )


def test_non_admin_cannot_see_private_peer_query() -> None:
    factory = app.state.session_factory
    row = sq.create_saved_query(
        factory,
        owner_id=_admin_id(),
        title="Admin private",
        description=None,
        sql_text="SELECT 1",
        is_shared=False,
    )
    # Non-admin lookup by slug should return None, not the row.
    got = sq.get_by_slug(factory, row["slug"], user_id=_non_admin_id(), is_admin=False)
    assert got is None
    # Listing for the non-admin does NOT include this slug.
    visible = sq.list_visible(factory, user_id=_non_admin_id(), is_admin=False)
    assert all(r["slug"] != row["slug"] for r in visible)


def test_shared_query_visible_to_every_logged_in_user() -> None:
    factory = app.state.session_factory
    row = sq.create_saved_query(
        factory,
        owner_id=_admin_id(),
        title="Shared report",
        description="see this",
        sql_text="SELECT * FROM main.sales.orders",
        is_shared=True,
    )
    visible = sq.list_visible(factory, user_id=_non_admin_id(), is_admin=False)
    assert any(r["slug"] == row["slug"] for r in visible)


def test_non_owner_cannot_update_or_delete() -> None:
    factory = app.state.session_factory
    row = sq.create_saved_query(
        factory,
        owner_id=_admin_id(),
        title="Admin only",
        description=None,
        sql_text="SELECT 1",
        is_shared=True,  # visible
    )
    # PATCH by non-owner: returns None.
    updated = sq.update_by_slug(
        factory,
        row["slug"],
        user_id=_non_admin_id(),
        is_admin=False,
        title="hacked",
    )
    assert updated is None

    # DELETE by non-owner: returns False.
    deleted = sq.delete_by_slug(factory, row["slug"], user_id=_non_admin_id(), is_admin=False)
    assert deleted is False

    # Original row still exists.
    fresh = sq.get_by_slug(factory, row["slug"], user_id=_admin_id(), is_admin=True)
    assert fresh is not None
    assert fresh["title"] == "Admin only"


def test_owner_can_toggle_sharing() -> None:
    factory = app.state.session_factory
    row = sq.create_saved_query(
        factory,
        owner_id=_admin_id(),
        title="Toggle me",
        description=None,
        sql_text="SELECT 1",
        is_shared=False,
    )
    shared = sq.update_by_slug(
        factory, row["slug"], user_id=_admin_id(), is_admin=True, is_shared=True
    )
    assert shared is not None
    assert shared["is_shared"] is True


# -- route-level ---------------------------------------------------


async def test_create_and_list_via_api(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/saved-queries",
        json={"title": "API test", "sql": "SELECT 1", "is_shared": False},
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["slug"].startswith("api-test-")
    slug = created["slug"]

    resp = await admin_client.get("/api/saved-queries")
    assert resp.status_code == 200
    lst = resp.json()
    assert any(r["slug"] == slug for r in lst)

    resp = await admin_client.get(f"/api/saved-queries/{slug}")
    assert resp.status_code == 200


async def test_non_admin_cannot_see_private_via_api(admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient) -> None:
    # Admin creates a private query.
    resp = await admin_client.post(
        "/api/saved-queries",
        json={"title": "Private admin", "sql": "SELECT 1", "is_shared": False},
    )
    assert resp.status_code == 200, resp.text
    slug = resp.json()["slug"]

    # Non-admin asks for it → 404.
    resp = await non_admin_client.get(f"/api/saved-queries/{slug}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "catalog_not_found"


async def test_patch_by_non_owner_returns_404(admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/saved-queries",
        json={"title": "Orig", "sql": "SELECT 1", "is_shared": True},
    )
    slug = resp.json()["slug"]

    resp = await non_admin_client.patch(
        f"/api/saved-queries/{slug}",
        json={"title": "hacked"},
    )
    assert resp.status_code == 404


async def test_delete_roundtrip_via_api(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/saved-queries",
        json={"title": "to delete", "sql": "SELECT 1"},
    )
    slug = resp.json()["slug"]

    resp = await admin_client.delete(f"/api/saved-queries/{slug}")
    assert resp.status_code == 204

    resp = await admin_client.get(f"/api/saved-queries/{slug}")
    assert resp.status_code == 404
