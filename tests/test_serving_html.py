"""The /serving cockpit page renders for any signed-in user.

The serving HTML router ships unregistered (the navigation
integration wires it into the bootstrap block later), so this module
mounts it onto the app for its own duration and removes the routes
on teardown — the session-global app stays pristine for other test
modules, and the fixture no-ops once the router is registered for
real.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api import serving_html_routes
from pointlessql.api.main import app


@pytest.fixture(autouse=True, scope="module")
def _mount_serving_router():
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/serving" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(serving_html_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.mark.asyncio
async def test_serving_renders_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    """Any signed-in user reaches the cockpit; no admin gate."""
    res = await non_admin_client.get("/serving")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="serving.js' in body
    assert "servingEndpoints(" in body
    assert "Model Serving" in body


@pytest.mark.asyncio
async def test_serving_renders_for_admin(admin_client: httpx.AsyncClient) -> None:
    """Admins see the same page."""
    res = await admin_client.get("/serving")
    assert res.status_code == 200
    assert "servingEndpoints(" in res.text


@pytest.mark.asyncio
async def test_serving_seeds_empty_endpoint_list(admin_client: httpx.AsyncClient) -> None:
    """A fresh workspace seeds the factory with an empty JSON list."""
    res = await admin_client.get("/serving")
    assert res.status_code == 200
    assert "servingEndpoints([])" in res.text


@pytest.mark.asyncio
async def test_serving_redirects_anonymous(anonymous_client: httpx.AsyncClient) -> None:
    """Anonymous HTML traffic bounces to the login page."""
    res = await anonymous_client.get("/serving", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"
