"""saved-views route CRUD + run smoke tests.

Verifies that the HTTP surface honours workspace scoping, SELECT-
only enforcement at create time, and the embed page renders.  Run
correctness lives in ``test_saved_views_service.py``; this file
only proves the route plumbing.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import SavedView


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        for row in session.query(SavedView).all():
            session.delete(row)
        session.commit()


@pytest.fixture(autouse=True)
def _clean() -> None:
    """Each test starts with an empty saved_views table."""
    _wipe()
    yield
    _wipe()


@pytest.mark.asyncio
async def test_create_round_trip(admin_client: httpx.AsyncClient) -> None:
    """POST → GET round-trip."""
    res = await admin_client.post(
        "/api/views",
        json={
            "title": "Top orders",
            "sql": "SELECT 1 AS n WHERE 1 = ${one}",
            "parameters": [{"name": "one", "type": "integer", "default": 1}],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    slug = body["slug"]
    assert body["title"] == "Top orders"
    assert body["parameters"][0]["name"] == "one"

    res = await admin_client.get(f"/api/views/{slug}")
    assert res.status_code == 200
    assert res.json()["slug"] == slug


@pytest.mark.asyncio
async def test_create_rejects_non_select(admin_client: httpx.AsyncClient) -> None:
    """A non-SELECT statement is rejected at save time."""
    res = await admin_client.post(
        "/api/views",
        json={"title": "Bad", "sql": "DROP TABLE foo"},
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_create_rejects_unbound_placeholder(
    admin_client: httpx.AsyncClient,
) -> None:
    """A ``${unknown}`` without a matching parameter is rejected."""
    res = await admin_client.post(
        "/api/views",
        json={"title": "Bad", "sql": "SELECT * FROM t WHERE c = ${nope}"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_list_includes_created(admin_client: httpx.AsyncClient) -> None:
    """Newly created views show up on the workspace list."""
    await admin_client.post(
        "/api/views",
        json={"title": "Alpha", "sql": "SELECT 1"},
    )
    res = await admin_client.get("/api/views")
    assert res.status_code == 200
    assert any(v["title"] == "Alpha" for v in res.json()["views"])


@pytest.mark.asyncio
async def test_patch_owner_only(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-owner non-admin gets 404, owner succeeds."""
    res = await admin_client.post(
        "/api/views",
        json={"title": "Alpha", "sql": "SELECT 1"},
    )
    slug = res.json()["slug"]
    # Non-admin (different user) cannot edit.
    res2 = await non_admin_client.patch(f"/api/views/{slug}", json={"title": "Hacked"})
    assert res2.status_code == 404
    # Owner / admin succeeds.
    res3 = await admin_client.patch(f"/api/views/{slug}", json={"title": "Renamed"})
    assert res3.status_code == 200
    assert res3.json()["title"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_owner_only(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Only owner / admin may delete; non-admin gets 404."""
    res = await admin_client.post("/api/views", json={"title": "Alpha", "sql": "SELECT 1"})
    slug = res.json()["slug"]
    res_del = await non_admin_client.delete(f"/api/views/{slug}")
    assert res_del.status_code == 404
    res_del2 = await admin_client.delete(f"/api/views/{slug}")
    assert res_del2.status_code == 204


@pytest.mark.asyncio
async def test_embed_page_renders(admin_client: httpx.AsyncClient) -> None:
    """The ``/views/{slug}/embed`` page returns 200 minimal-chrome."""
    res = await admin_client.post("/api/views", json={"title": "Embed me", "sql": "SELECT 1"})
    slug = res.json()["slug"]
    page = await admin_client.get(f"/views/{slug}/embed")
    assert page.status_code == 200
    # Embed should not include the primary-rail container.
    assert "pql-icon-rail__link" not in page.text
    assert "Embed me" in page.text


@pytest.mark.asyncio
async def test_views_list_page_renders(admin_client: httpx.AsyncClient) -> None:
    """The ``/views`` page returns 200."""
    page = await admin_client.get("/views")
    assert page.status_code == 200
    assert "Saved views" in page.text


@pytest.mark.asyncio
async def test_new_page_renders(admin_client: httpx.AsyncClient) -> None:
    """The ``/views/new`` page returns 200."""
    page = await admin_client.get("/views/new")
    assert page.status_code == 200
    assert "New saved view" in page.text


@pytest.mark.asyncio
async def test_404_for_unknown_slug(admin_client: httpx.AsyncClient) -> None:
    """Unknown slug returns 404."""
    res = await admin_client.get("/api/views/no-such-slug")
    assert res.status_code == 404
