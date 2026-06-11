"""The Delta Sharing HTML pages render for the right principals.

``/admin/sharing`` is admin-gated (403 otherwise); ``/shared-with-me``
is open to any signed-in user.  The sharing HTML router ships
unregistered (the navigation integration wires it into the bootstrap
block later), so this module mounts it onto the app for its own
duration and removes the routes on teardown — the fixture no-ops once
the router is registered for real.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api import sharing_html_routes
from pointlessql.api.main import app


@pytest.fixture(autouse=True, scope="module")
def _mount_sharing_router():
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/admin/sharing" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(sharing_html_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


class TestAdminSharingPage:
    """Provider cockpit: admin-only."""

    @pytest.mark.asyncio
    async def test_renders_for_admin(self, admin_client: httpx.AsyncClient) -> None:
        res = await admin_client.get("/admin/sharing")
        assert res.status_code == 200
        body = res.text
        assert 'data-pql-entry="admin_sharing.js' in body
        assert "adminSharing(" in body
        assert "Delta Sharing" in body

    @pytest.mark.asyncio
    async def test_403_for_non_admin(self, non_admin_client: httpx.AsyncClient) -> None:
        res = await non_admin_client.get("/admin/sharing")
        assert res.status_code == 403

    @pytest.mark.asyncio
    async def test_redirects_anonymous(self, anonymous_client: httpx.AsyncClient) -> None:
        res = await anonymous_client.get("/admin/sharing", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/auth/login"


class TestSharedWithMePage:
    """Consumer browser: any signed-in user."""

    @pytest.mark.asyncio
    async def test_renders_for_non_admin(self, non_admin_client: httpx.AsyncClient) -> None:
        res = await non_admin_client.get("/shared-with-me")
        assert res.status_code == 200
        body = res.text
        assert 'data-pql-entry="shared_with_me.js' in body
        assert "sharedWithMe(" in body
        assert "Shared with me" in body

    @pytest.mark.asyncio
    async def test_renders_for_admin(self, admin_client: httpx.AsyncClient) -> None:
        res = await admin_client.get("/shared-with-me")
        assert res.status_code == 200
        assert "sharedWithMe(" in res.text

    @pytest.mark.asyncio
    async def test_redirects_anonymous(self, anonymous_client: httpx.AsyncClient) -> None:
        res = await anonymous_client.get("/shared-with-me", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/auth/login"
