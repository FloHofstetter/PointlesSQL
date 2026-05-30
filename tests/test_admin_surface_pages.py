"""Surface-Welle admin pages render under the admin auth gate."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app


ADMIN_SURFACE_PATHS = [
    "/admin/policy-modules",
    "/admin/mesh-dashboard",
    "/admin/entity-discovery",
    "/admin/data-product-apply",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_SURFACE_PATHS)
async def test_admin_surface_page_renders_for_admin(path: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get(path)
    assert res.status_code == 200, res.text
    assert "<html" in res.text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_SURFACE_PATHS)
async def test_admin_surface_page_rejects_non_admin(path: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.get(path)
    assert res.status_code in (401, 403)
