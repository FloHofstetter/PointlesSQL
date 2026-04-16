"""Tests for API error handling when soyuz-catalog is unreachable."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_failing_mock() -> MagicMock:
    """Build a UnityCatalogClient mock whose methods raise CatalogUnavailableError."""
    client = MagicMock(spec=UnityCatalogClient)
    err = CatalogUnavailableError("Catalog server unavailable: Connection refused")

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
    """Wire app.state with a UnityCatalogClient whose methods raise CatalogUnavailableError.

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


def _assert_502_json(resp: httpx.Response) -> None:
    """Assert a response matches the centralized 502 JSON error envelope."""
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "catalog_unavailable"
    assert "Connection refused" in body["error"]["message"]
    assert "request_id" in body["error"]


class TestJsonEndpointsReturn502:
    async def test_api_tree(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        _assert_502_json(resp)

    async def test_api_catalogs(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs")
        _assert_502_json(resp)

    async def test_api_schemas(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs/test_cat/schemas")
        _assert_502_json(resp)

    async def test_api_tables(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs/test_cat/schemas/test_sch/tables")
        _assert_502_json(resp)

    async def test_patch_catalog(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/catalogs/test_cat", json={"comment": "hi"}
            )
        _assert_502_json(resp)

    async def test_patch_schema(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/catalogs/test_cat/schemas/test_sch",
                json={"comment": "hi"},
            )
        _assert_502_json(resp)

    async def test_get_tags(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/tags/catalog/test_cat")
        _assert_502_json(resp)

    async def test_patch_tags(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/tags/catalog/test_cat",
                json={"changes": [{"key": "k", "op": "set", "value": "v"}]},
            )
        _assert_502_json(resp)

    async def test_get_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/permissions/catalog/test_cat")
        _assert_502_json(resp)

    async def test_patch_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.patch(
                "/api/permissions/catalog/test_cat",
                json={"changes": []},
            )
        _assert_502_json(resp)

    async def test_get_effective_permissions(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/effective-permissions/catalog/test_cat")
        _assert_502_json(resp)

    async def test_get_lineage(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/lineage/cat.sch.tbl")
        _assert_502_json(resp)

    async def test_list_connections(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/connections")
        _assert_502_json(resp)

    async def test_create_connection(self) -> None:
        async with _authed_client() as client:
            resp = await client.post(
                "/api/connections",
                json={"name": "test", "connection_type": "POSTGRESQL"},
            )
        _assert_502_json(resp)

    async def test_delete_connection(self) -> None:
        async with _authed_client() as client:
            resp = await client.delete("/api/connections/test")
        _assert_502_json(resp)

    async def test_list_external_locations(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/external-locations")
        _assert_502_json(resp)

    async def test_list_credentials(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/credentials")
        _assert_502_json(resp)

    async def test_request_id_in_header(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert "X-Request-ID" in resp.headers

    async def test_request_id_forwarded(self) -> None:
        async with _authed_client() as client:
            resp = await client.get(
                "/api/tree", headers={"X-Request-ID": "test-req-123"}
            )
        assert resp.headers["X-Request-ID"] == "test-req-123"
        assert resp.json()["error"]["request_id"] == "test-req-123"


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
