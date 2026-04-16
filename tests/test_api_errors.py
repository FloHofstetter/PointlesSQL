"""Tests for API error handling when soyuz-catalog is unreachable."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.settings import Settings


@pytest.fixture(autouse=True)
def _app_with_failing_client() -> None:
    """Wire app.state with a UnityCatalogClient whose methods raise ConnectError."""
    client = MagicMock()
    err = httpx.ConnectError("Connection refused")

    client.get_tree = AsyncMock(side_effect=err)
    client.list_catalogs = AsyncMock(side_effect=err)
    client.list_schemas = AsyncMock(side_effect=err)
    client.list_tables = AsyncMock(side_effect=err)
    client.update_catalog = AsyncMock(side_effect=err)
    client.update_schema = AsyncMock(side_effect=err)

    app.state.uc_client = client
    app.state.settings = Settings(jupyter_enabled=False)
    app.state.jupyter_process = None


class TestJsonEndpointsReturn502:
    async def test_api_tree(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_catalogs(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/catalogs")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_schemas(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/catalogs/test_cat/schemas")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_tables(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/catalogs/test_cat/schemas/test_sch/tables")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_catalog(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/catalogs/test_cat", json={"comment": "hi"}
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_schema(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/api/catalogs/test_cat/schemas/test_sch",
                json={"comment": "hi"},
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]


class TestHtmlPagesShowError:
    async def test_catalogs_index(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        assert "Connection refused" in resp.text

    async def test_catalog_detail(self) -> None:
        app.state.uc_client.get_catalog = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/catalogs/test_cat")
        assert resp.status_code == 200
        assert "Connection refused" in resp.text
