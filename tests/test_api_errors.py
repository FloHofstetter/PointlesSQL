"""Tests for API error handling when soyuz-catalog is unreachable."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_failing_mock() -> MagicMock:
    """Build a UnityCatalogClient mock whose methods raise ConnectError."""
    client = MagicMock(spec=UnityCatalogClient)
    err = httpx.ConnectError("Connection refused")

    client.get_tree = AsyncMock(side_effect=err)
    client.list_catalogs = AsyncMock(side_effect=err)
    client.list_schemas = AsyncMock(side_effect=err)
    client.list_tables = AsyncMock(side_effect=err)
    client.update_catalog = AsyncMock(side_effect=err)
    client.update_schema = AsyncMock(side_effect=err)
    client.get_tags = AsyncMock(side_effect=err)
    client.update_tags = AsyncMock(side_effect=err)
    client.get_permissions = AsyncMock(side_effect=err)
    client.update_permissions = AsyncMock(side_effect=err)
    client.get_effective_permissions = AsyncMock(side_effect=err)
    client.get_lineage = AsyncMock(side_effect=err)
    client.list_connections = AsyncMock(side_effect=err)
    client.get_connection = AsyncMock(side_effect=err)
    client.create_connection = AsyncMock(side_effect=err)
    client.update_connection = AsyncMock(side_effect=err)
    client.delete_connection = AsyncMock(side_effect=err)
    client.list_external_locations = AsyncMock(side_effect=err)
    client.get_external_location = AsyncMock(side_effect=err)
    client.create_external_location = AsyncMock(side_effect=err)
    client.update_external_location = AsyncMock(side_effect=err)
    client.delete_external_location = AsyncMock(side_effect=err)
    client.list_credentials = AsyncMock(side_effect=err)
    client.get_credential = AsyncMock(side_effect=err)
    client.create_credential = AsyncMock(side_effect=err)
    client.update_credential = AsyncMock(side_effect=err)
    client.delete_credential = AsyncMock(side_effect=err)
    return client


@pytest.fixture(autouse=True)
def _app_with_failing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire app.state with a UnityCatalogClient whose methods raise ConnectError.

    Patches ``UnityCatalogClient.for_principal`` so the per-request
    client factory returns our mock instead of creating a real client.
    """
    client = _make_failing_mock()
    app.state.uc_client = client
    app.state.jupyter_process = None

    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
    )


def _authed_client() -> httpx.AsyncClient:
    """Return an httpx.AsyncClient pre-authenticated with the test user cookie."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


class TestJsonEndpointsReturn502:
    async def test_api_tree(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_catalogs(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_schemas(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs/test_cat/schemas")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_api_tables(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs/test_cat/schemas/test_sch/tables")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_catalog(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/catalogs/test_cat", json={"comment": "hi"}
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_schema(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/catalogs/test_cat/schemas/test_sch",
                json={"comment": "hi"},
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_get_tags(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/tags/catalog/test_cat")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_tags(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/tags/catalog/test_cat",
                json={"changes": [{"key": "k", "op": "set", "value": "v"}]},
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_get_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/permissions/catalog/test_cat")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_patch_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/permissions/catalog/test_cat",
                json={"changes": []},
            )
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_get_effective_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/effective-permissions/catalog/test_cat")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_get_lineage(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/lineage/cat.sch.tbl")
        assert resp.status_code == 502
        assert "Catalog server unavailable" in resp.json()["error"]

    async def test_list_connections(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/connections")
        assert resp.status_code == 502

    async def test_create_connection(self) -> None:
        async with _authed_client() as client:
            resp = await client.post(
                "/api/connections",
                json={"name": "test", "connection_type": "POSTGRESQL"},
            )
        assert resp.status_code == 502

    async def test_delete_connection(self) -> None:
        async with _authed_client() as client:
            resp = await client.delete("/api/connections/test")
        assert resp.status_code == 502

    async def test_list_external_locations(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/external-locations")
        assert resp.status_code == 502

    async def test_list_credentials(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/credentials")
        assert resp.status_code == 502


class TestHtmlPagesShowError:
    async def test_catalogs_index(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        assert "Connection refused" in resp.text

    async def test_catalog_detail(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/catalogs/test_cat")
        assert resp.status_code == 200
        assert "Connection refused" in resp.text
