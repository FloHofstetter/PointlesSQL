"""HTML-page tests for the AI/BI dashboards surface (/bi + public viewer)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api.main import app


def _client(cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies or {},
    )


async def _create(cookies: dict[str, str], title: str) -> dict[str, Any]:
    async with _client(cookies) as client:
        resp = await client.post("/api/bi/dashboards", json={"title": title})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_list_page_renders_with_entry_and_factory() -> None:
    await _create(app.state._test_auth_cookie, "List Page Board")
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get("/bi")
    assert page.status_code == 200
    assert "bi_dashboards.js" in page.text
    assert 'x-data="biDashboardsList()"' in page.text
    assert "List Page Board" in page.text


@pytest.mark.asyncio
async def test_list_page_requires_login() -> None:
    async with _client() as client:
        resp = await client.get("/bi")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_view_page_renders_for_any_user_with_owner_affordances() -> None:
    body = await _create(app.state._test_non_admin_cookie, "Owner View Board")
    slug = body["slug"]
    async with _client(app.state._test_non_admin_cookie) as client:
        page = await client.get(f"/bi/{slug}")
    assert page.status_code == 200
    assert "bi_dashboard_view.js" in page.text
    assert "biDashboardView(" in page.text
    assert f'href="/bi/{slug}/edit"' in page.text  # owner sees Edit


@pytest.mark.asyncio
async def test_view_page_hides_edit_affordances_for_non_owner() -> None:
    body = await _create(app.state._test_auth_cookie, "Admin Owned Board")
    slug = body["slug"]
    async with _client(app.state._test_non_admin_cookie) as client:
        page = await client.get(f"/bi/{slug}")
    assert page.status_code == 200
    assert f'href="/bi/{slug}/edit"' not in page.text


@pytest.mark.asyncio
async def test_view_page_unknown_slug_404s() -> None:
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get("/bi/no-such-board-000000")
    assert page.status_code == 404


@pytest.mark.asyncio
async def test_edit_page_gated_to_owner_and_admin() -> None:
    body = await _create(app.state._test_auth_cookie, "Gated Edit Board")
    slug = body["slug"]
    async with _client(app.state._test_non_admin_cookie) as client:
        denied = await client.get(f"/bi/{slug}/edit")
    assert denied.status_code == 403
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get(f"/bi/{slug}/edit")
    assert page.status_code == 200
    assert "bi_dashboard_edit.js" in page.text
    assert "biDashboardEdit(" in page.text


@pytest.mark.asyncio
async def test_edit_page_renders_for_non_admin_owner() -> None:
    body = await _create(app.state._test_non_admin_cookie, "Own Edit Board")
    async with _client(app.state._test_non_admin_cookie) as client:
        page = await client.get(f"/bi/{body['slug']}/edit")
    assert page.status_code == 200


@pytest.mark.asyncio
async def test_public_page_publish_unpublish_lifecycle() -> None:
    body = await _create(app.state._test_auth_cookie, "Public Board")
    slug = body["slug"]
    async with _client(app.state._test_auth_cookie) as client:
        widget = await client.post(
            f"/api/bi/dashboards/{slug}/widgets",
            json={"kind": "markdown", "title": "Note", "markdown": "## Hello public"},
        )
        assert widget.status_code == 200, widget.text
        published = await client.post(f"/api/bi/dashboards/{slug}/publish", json={"publish": True})
        assert published.status_code == 200, published.text
        token = published.json()["public_token"]
    assert token

    # Anonymous viewer: no cookies at all.
    async with _client() as client:
        page = await client.get(f"/bi/public/{token}")
    assert page.status_code == 200
    assert "biDashboardView(" in page.text
    assert token in page.text  # config wires the public data path

    async with _client(app.state._test_auth_cookie) as client:
        await client.post(f"/api/bi/dashboards/{slug}/publish", json={"publish": False})
    async with _client() as client:
        gone = await client.get(f"/bi/public/{token}")
    assert gone.status_code == 404
