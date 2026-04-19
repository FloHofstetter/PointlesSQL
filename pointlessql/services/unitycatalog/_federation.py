"""Federation surfaces: connections, external locations, credentials."""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.connection_info import ConnectionInfo
from soyuz_catalog_client.models.create_connection import CreateConnection
from soyuz_catalog_client.models.create_credential_request import (
    CreateCredentialRequest,
)
from soyuz_catalog_client.models.create_external_location import (
    CreateExternalLocation,
)
from soyuz_catalog_client.models.credential_info import CredentialInfo
from soyuz_catalog_client.models.external_location_info import ExternalLocationInfo
from soyuz_catalog_client.models.list_connections_response import (
    ListConnectionsResponse,
)
from soyuz_catalog_client.models.list_credentials_response import (
    ListCredentialsResponse,
)
from soyuz_catalog_client.models.list_external_locations_response import (
    ListExternalLocationsResponse,
)
from soyuz_catalog_client.models.update_connection import UpdateConnection
from soyuz_catalog_client.models.update_credential_request import (
    UpdateCredentialRequest,
)
from soyuz_catalog_client.models.update_external_location import (
    UpdateExternalLocation,
)

from pointlessql.services.unitycatalog._api import (
    _create_connection,
    _create_credential,
    _create_ext_loc,
    _delete_connection,
    _delete_credential,
    _delete_ext_loc,
    _get_connection,
    _get_credential,
    _get_ext_loc,
    _list_connections,
    _list_credentials,
    _list_ext_locs,
    _update_connection,
    _update_credential,
    _update_ext_loc,
    wrap_catalog_errors,
)


class FederationMixin:
    """Connections, external locations, and credentials CRUD."""

    _client: Client  # provided by UnityCatalogClient

    # -- Connections --

    @wrap_catalog_errors
    async def list_connections(self) -> list[dict[str, Any]]:
        """Return all federation connections."""
        response = await _list_connections.asyncio(client=self._client)
        if not isinstance(response, ListConnectionsResponse):
            return []
        return [c.to_dict() for c in response.connections]

    @wrap_catalog_errors
    async def get_connection(self, name: str) -> dict[str, Any]:
        """Return a single connection by name."""
        response = await _get_connection.asyncio(name=name, client=self._client)
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_connection(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new connection."""
        body = CreateConnection.from_dict(data)
        response = await _create_connection.asyncio(client=self._client, body=body)
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_connection(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update an existing connection."""
        body = UpdateConnection.from_dict(patch)
        response = await _update_connection.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_connection(self, name: str) -> None:
        """Delete a connection."""
        await _delete_connection.asyncio(name=name, client=self._client)

    # -- External Locations --

    @wrap_catalog_errors
    async def list_external_locations(self) -> list[dict[str, Any]]:
        """Return all external locations."""
        response = await _list_ext_locs.asyncio(client=self._client)
        if not isinstance(response, ListExternalLocationsResponse):
            return []
        return [e.to_dict() for e in response.external_locations]

    @wrap_catalog_errors
    async def get_external_location(self, name: str) -> dict[str, Any]:
        """Return a single external location by name."""
        response = await _get_ext_loc.asyncio(name=name, client=self._client)
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_external_location(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new external location."""
        body = CreateExternalLocation.from_dict(data)
        response = await _create_ext_loc.asyncio(client=self._client, body=body)
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_external_location(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update an existing external location."""
        body = UpdateExternalLocation.from_dict(patch)
        response = await _update_ext_loc.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_external_location(self, name: str) -> None:
        """Delete an external location."""
        await _delete_ext_loc.asyncio(name=name, client=self._client)

    # -- Credentials --

    @wrap_catalog_errors
    async def list_credentials(self) -> list[dict[str, Any]]:
        """Return all credentials."""
        response = await _list_credentials.asyncio(client=self._client)
        if not isinstance(response, ListCredentialsResponse):
            return []
        return [c.to_dict() for c in response.credentials]

    @wrap_catalog_errors
    async def get_credential(self, name: str) -> dict[str, Any]:
        """Return a single credential by name."""
        response = await _get_credential.asyncio(name=name, client=self._client)
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_credential(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new credential."""
        body = CreateCredentialRequest.from_dict(data)
        response = await _create_credential.asyncio(client=self._client, body=body)
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_credential(self, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update an existing credential."""
        body = UpdateCredentialRequest.from_dict(patch)
        response = await _update_credential.asyncio(name=name, client=self._client, body=body)
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_credential(self, name: str) -> None:
        """Delete a credential."""
        await _delete_credential.asyncio(name=name, client=self._client)
