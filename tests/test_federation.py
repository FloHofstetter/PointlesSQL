"""Unit tests for federation facade methods (connections, ext locations, credentials)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_client() -> UnityCatalogClient:
    """Return a UnityCatalogClient backed by a mock soyuz client."""
    mock = MagicMock()
    return UnityCatalogClient(mock)


class TestConnections:
    async def test_list_connections(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.list_connections_response import (
            ListConnectionsResponse,
        )

        conn = MagicMock()
        conn.to_dict.return_value = {"name": "pg", "connection_type": "POSTGRESQL"}
        resp = MagicMock(spec=ListConnectionsResponse)
        resp.connections = [conn]

        with patch(
            "pointlessql.services.unitycatalog._list_connections.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.list_connections()

        assert result == [{"name": "pg", "connection_type": "POSTGRESQL"}]

    async def test_list_connections_empty(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._list_connections.asyncio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await uc_client.list_connections()

        assert result == []

    async def test_get_connection(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.connection_info import ConnectionInfo

        resp = MagicMock(spec=ConnectionInfo)
        resp.to_dict.return_value = {"name": "pg", "connection_type": "POSTGRESQL"}

        with patch(
            "pointlessql.services.unitycatalog._get_connection.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.get_connection("pg")

        assert result["name"] == "pg"

    async def test_create_connection(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.connection_info import ConnectionInfo

        resp = MagicMock(spec=ConnectionInfo)
        resp.to_dict.return_value = {"name": "pg", "connection_type": "POSTGRESQL"}

        with patch(
            "pointlessql.services.unitycatalog._create_connection.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.create_connection(
                {"name": "pg", "connection_type": "POSTGRESQL"}
            )

        assert result["name"] == "pg"

    async def test_delete_connection(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._delete_connection.asyncio",
            new_callable=AsyncMock,
        ):
            await uc_client.delete_connection("pg")


class TestCatalogsCreate:
    async def test_create_managed_catalog(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.catalog_info import CatalogInfo

        resp = MagicMock(spec=CatalogInfo)
        resp.to_dict.return_value = {"name": "managed_cat", "type": "MANAGED"}

        with patch(
            "pointlessql.services.unitycatalog._create_catalog.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.create_catalog({"name": "managed_cat"})

        assert result == {"name": "managed_cat", "type": "MANAGED"}

    async def test_create_foreign_catalog(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.catalog_info import CatalogInfo

        resp = MagicMock(spec=CatalogInfo)
        resp.to_dict.return_value = {
            "name": "pg_cat",
            "type": "FOREIGN",
            "connection_name": "my_pg",
            "options": {"database": "analytics"},
        }

        with patch(
            "pointlessql.services.unitycatalog._create_catalog.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ) as mock:
            result = await uc_client.create_catalog(
                {
                    "name": "pg_cat",
                    "type": "FOREIGN",
                    "connection_name": "my_pg",
                    "options": {"database": "analytics"},
                }
            )

        assert result["connection_name"] == "my_pg"
        assert result["options"] == {"database": "analytics"}
        # Ensure the typed model round-tripped the foreign fields.
        body = mock.call_args.kwargs["body"]
        assert body.name == "pg_cat"
        assert body.connection_name == "my_pg"

    async def test_create_catalog_empty_response(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._create_catalog.asyncio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await uc_client.create_catalog({"name": "x"})
        assert result == {}

    async def test_delete_catalog(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._delete_catalog.asyncio",
            new_callable=AsyncMock,
        ) as mock:
            await uc_client.delete_catalog("cat", force=True)
        assert mock.call_args.kwargs["force"] is True


class TestExternalLocations:
    async def test_list_external_locations(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.list_external_locations_response import (
            ListExternalLocationsResponse,
        )

        loc = MagicMock()
        loc.to_dict.return_value = {"name": "s3_bucket", "url": "s3://bucket"}
        resp = MagicMock(spec=ListExternalLocationsResponse)
        resp.external_locations = [loc]

        with patch(
            "pointlessql.services.unitycatalog._list_ext_locs.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.list_external_locations()

        assert result == [{"name": "s3_bucket", "url": "s3://bucket"}]

    async def test_get_external_location(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.external_location_info import (
            ExternalLocationInfo,
        )

        resp = MagicMock(spec=ExternalLocationInfo)
        resp.to_dict.return_value = {"name": "s3_bucket", "url": "s3://bucket"}

        with patch(
            "pointlessql.services.unitycatalog._get_ext_loc.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.get_external_location("s3_bucket")

        assert result["name"] == "s3_bucket"

    async def test_delete_external_location(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._delete_ext_loc.asyncio",
            new_callable=AsyncMock,
        ):
            await uc_client.delete_external_location("s3_bucket")


class TestCredentials:
    async def test_list_credentials(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.list_credentials_response import (
            ListCredentialsResponse,
        )

        cred = MagicMock()
        cred.to_dict.return_value = {"name": "my_cred", "purpose": "STORAGE"}
        resp = MagicMock(spec=ListCredentialsResponse)
        resp.credentials = [cred]

        with patch(
            "pointlessql.services.unitycatalog._list_credentials.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.list_credentials()

        assert result == [{"name": "my_cred", "purpose": "STORAGE"}]

    async def test_get_credential(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.credential_info import CredentialInfo

        resp = MagicMock(spec=CredentialInfo)
        resp.to_dict.return_value = {"name": "my_cred", "purpose": "STORAGE"}

        with patch(
            "pointlessql.services.unitycatalog._get_credential.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.get_credential("my_cred")

        assert result["name"] == "my_cred"

    async def test_create_credential(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.credential_info import CredentialInfo

        resp = MagicMock(spec=CredentialInfo)
        resp.to_dict.return_value = {"name": "my_cred", "purpose": "STORAGE"}

        with patch(
            "pointlessql.services.unitycatalog._create_credential.asyncio",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await uc_client.create_credential({"name": "my_cred", "purpose": "STORAGE"})

        assert result["name"] == "my_cred"

    async def test_delete_credential(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._delete_credential.asyncio",
            new_callable=AsyncMock,
        ):
            await uc_client.delete_credential("my_cred")
