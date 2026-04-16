"""Async wrapper around the generated soyuz-catalog client.

Delegates every HTTP call to the typed functions shipped with
``soyuz_catalog_client`` and converts the attrs response objects back
to plain dicts so that FastAPI routes and Jinja2 templates can consume
them without changes.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.catalogs import (
    create_catalog_api_2_1_unity_catalog_catalogs_post as _create_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    delete_catalog_api_2_1_unity_catalog_catalogs_name_delete as _delete_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    get_catalog_api_2_1_unity_catalog_catalogs_name_get as _get_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    list_catalogs_api_2_1_unity_catalog_catalogs_get as _list_catalogs,
)
from soyuz_catalog_client.api.catalogs import (
    update_catalog_api_2_1_unity_catalog_catalogs_name_patch as _update_catalog,
)
from soyuz_catalog_client.api.connections import (
    create_connection_api_2_1_unity_catalog_connections_post as _create_connection,
)
from soyuz_catalog_client.api.connections import (
    delete_connection_api_2_1_unity_catalog_connections_name_delete as _delete_connection,
)
from soyuz_catalog_client.api.connections import (
    get_connection_api_2_1_unity_catalog_connections_name_get as _get_connection,
)
from soyuz_catalog_client.api.connections import (
    list_connections_api_2_1_unity_catalog_connections_get as _list_connections,
)
from soyuz_catalog_client.api.connections import (
    update_connection_api_2_1_unity_catalog_connections_name_patch as _update_connection,
)
from soyuz_catalog_client.api.credentials import (
    create_credential_api_2_1_unity_catalog_credentials_post as _create_credential,
)
from soyuz_catalog_client.api.credentials import (
    delete_credential_api_2_1_unity_catalog_credentials_name_delete as _delete_credential,
)
from soyuz_catalog_client.api.credentials import (
    get_credential_api_2_1_unity_catalog_credentials_name_get as _get_credential,
)
from soyuz_catalog_client.api.credentials import (
    list_credentials_api_2_1_unity_catalog_credentials_get as _list_credentials,
)
from soyuz_catalog_client.api.credentials import (
    update_credential_api_2_1_unity_catalog_credentials_name_patch as _update_credential,
)
from soyuz_catalog_client.api.effective_permissions import (
    get_effective_permissions_api_2_1_unity_catalog_effective_permissions_securable_type_full_name_get as _get_effective_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.external_locations import (
    create_external_location_api_2_1_unity_catalog_external_locations_post as _create_ext_loc,
)
from soyuz_catalog_client.api.external_locations import (
    delete_external_location_api_2_1_unity_catalog_external_locations_name_delete as _delete_ext_loc,  # noqa: E501
)
from soyuz_catalog_client.api.external_locations import (
    get_external_location_api_2_1_unity_catalog_external_locations_name_get as _get_ext_loc,
)
from soyuz_catalog_client.api.external_locations import (
    list_external_locations_api_2_1_unity_catalog_external_locations_get as _list_ext_locs,
)
from soyuz_catalog_client.api.external_locations import (
    update_external_location_api_2_1_unity_catalog_external_locations_name_patch as _update_ext_loc,
)
from soyuz_catalog_client.api.lineage import (
    get_downstream_lineage_downstream_full_name_get as _get_downstream,
)
from soyuz_catalog_client.api.lineage import (
    get_upstream_lineage_upstream_full_name_get as _get_upstream,
)
from soyuz_catalog_client.api.permissions import (
    get_permissions_api_2_1_unity_catalog_permissions_securable_type_full_name_get as _get_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.permissions import (
    update_permissions_api_2_1_unity_catalog_permissions_securable_type_full_name_patch as _update_permissions,  # noqa: E501
)
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.schemas import (
    list_schemas_api_2_1_unity_catalog_schemas_get as _list_schemas,
)
from soyuz_catalog_client.api.schemas import (
    update_schema_api_2_1_unity_catalog_schemas_full_name_patch as _update_schema,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.api.tags import (
    get_tags_tags_securable_type_full_name_get as _get_tags,
)
from soyuz_catalog_client.api.tags import (
    update_tags_tags_securable_type_full_name_patch as _update_tags,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.catalog_info import CatalogInfo
from soyuz_catalog_client.models.connection_info import ConnectionInfo
from soyuz_catalog_client.models.create_catalog import CreateCatalog
from soyuz_catalog_client.models.create_connection import CreateConnection
from soyuz_catalog_client.models.create_credential_request import (
    CreateCredentialRequest,
)
from soyuz_catalog_client.models.create_external_location import (
    CreateExternalLocation,
)
from soyuz_catalog_client.models.credential_info import CredentialInfo
from soyuz_catalog_client.models.external_location_info import ExternalLocationInfo
from soyuz_catalog_client.models.get_effective_permissions_api_21_unity_catalog_effective_permissions_securable_type_full_name_get_securable_type import (  # noqa: E501
    GetEffectivePermissionsApi21UnityCatalogEffectivePermissionsSecurableTypeFullNameGetSecurableType,  # noqa: E501
)
from soyuz_catalog_client.models.get_permissions_api_21_unity_catalog_permissions_securable_type_full_name_get_securable_type import (  # noqa: E501
    GetPermissionsApi21UnityCatalogPermissionsSecurableTypeFullNameGetSecurableType,
)
from soyuz_catalog_client.models.get_tags_tags_securable_type_full_name_get_securable_type import (
    GetTagsTagsSecurableTypeFullNameGetSecurableType,
)
from soyuz_catalog_client.models.lineage_graph_response import LineageGraphResponse
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_connections_response import (
    ListConnectionsResponse,
)
from soyuz_catalog_client.models.list_credentials_response import (
    ListCredentialsResponse,
)
from soyuz_catalog_client.models.list_external_locations_response import (
    ListExternalLocationsResponse,
)
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.permissions_list import PermissionsList
from soyuz_catalog_client.models.tag_list import TagList
from soyuz_catalog_client.models.update_catalog import UpdateCatalog
from soyuz_catalog_client.models.update_connection import UpdateConnection
from soyuz_catalog_client.models.update_credential_request import (
    UpdateCredentialRequest,
)
from soyuz_catalog_client.models.update_external_location import (
    UpdateExternalLocation,
)
from soyuz_catalog_client.models.update_permissions import UpdatePermissions
from soyuz_catalog_client.models.update_permissions_api_21_unity_catalog_permissions_securable_type_full_name_patch_securable_type import (  # noqa: E501
    UpdatePermissionsApi21UnityCatalogPermissionsSecurableTypeFullNamePatchSecurableType,
)
from soyuz_catalog_client.models.update_schema import UpdateSchema
from soyuz_catalog_client.models.update_tags import UpdateTags
from soyuz_catalog_client.models.update_tags_tags_securable_type_full_name_patch_securable_type import (  # noqa: E501
    UpdateTagsTagsSecurableTypeFullNamePatchSecurableType,
)

from pointlessql.exceptions import CatalogUnavailableError

logger = logging.getLogger(__name__)


def _wrap_catalog_errors[T](
    fn: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wrap an async method so transport errors become domain exceptions."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await fn(*args, **kwargs)
        except (httpx.HTTPError, UnexpectedStatus) as exc:
            # Log the original transport-level exception before it gets
            # re-raised as the domain exception — otherwise the exact
            # failure mode (timeout vs. 500 vs. connection refused) is
            # lost once CatalogUnavailableError replaces it upstream.
            logger.warning(
                "soyuz-catalog request failed in %s", fn.__name__, exc_info=True
            )
            raise CatalogUnavailableError(
                f"Catalog server unavailable: {exc}"
            ) from exc

    return wrapper


class UnityCatalogClient:
    """Async facade over the generated soyuz-catalog client.

    Args:
        client: A configured ``soyuz_catalog_client.Client`` instance,
            typically built by :func:`pointlessql.services.soyuz_client.make_soyuz_client`.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    def for_principal(
        cls, settings: object, principal: str
    ) -> UnityCatalogClient:
        """Create a per-request facade with an ``X-Principal`` header.

        Args:
            settings: Application settings (needs ``soyuz_catalog_url``).
            principal: The user email to forward as the acting principal.

        Returns:
            A new ``UnityCatalogClient`` whose underlying HTTP client
            sends the ``X-Principal`` header on every request.
        """
        from pointlessql.services.soyuz_client import make_principal_client

        return cls(make_principal_client(settings, principal))  # type: ignore[arg-type]

    async def aclose(self) -> None:
        """Release the underlying HTTP resources."""
        await self._client.__aexit__()

    @_wrap_catalog_errors
    async def list_catalogs(self) -> list[dict[str, Any]]:
        """Return all catalogs visible to the caller.

        Returns:
            A list of catalog dicts, or an empty list if the server
            reports none.
        """
        response = await _list_catalogs.asyncio(client=self._client)
        if not isinstance(response, ListCatalogsResponse):
            return []
        catalogs = response.catalogs
        if not isinstance(catalogs, list):
            return []
        return [c.to_dict() for c in catalogs]

    @_wrap_catalog_errors
    async def get_catalog(self, catalog_name: str) -> dict[str, Any]:
        """Return metadata for a single catalog."""
        response = await _get_catalog.asyncio(name=catalog_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def get_schema(
        self, catalog_name: str, schema_name: str
    ) -> dict[str, Any]:
        """Return metadata for a single schema."""
        full_name = f"{catalog_name}.{schema_name}"
        response = await _get_schema.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def get_table(
        self, catalog_name: str, schema_name: str, table_name: str
    ) -> dict[str, Any]:
        """Return metadata (including columns) for a single table."""
        full_name = f"{catalog_name}.{schema_name}.{table_name}"
        response = await _get_table.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def create_catalog(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new catalog (managed or foreign).

        Foreign catalogs are the Sprint 28 variant in soyuz-catalog: pass
        ``type="FOREIGN"`` together with ``connection_name`` and optional
        per-connector ``options``. Managed catalogs default to
        ``type="MANAGED"``; passing a ``storage_root`` is optional.

        Args:
            data: Request body matching ``CreateCatalog`` — at minimum
                ``name``; for foreign variants ``connection_name`` and
                ``type`` must be set.

        Returns:
            The created catalog as returned by soyuz-catalog, or an empty
            dict when the server returned no parsed body.
        """
        body = CreateCatalog.from_dict(data)
        response = await _create_catalog.asyncio(client=self._client, body=body)
        if not isinstance(response, CatalogInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def delete_catalog(self, catalog_name: str, force: bool = False) -> None:
        """Delete a catalog.

        Args:
            catalog_name: Target catalog.
            force: When ``True``, soyuz-catalog cascades the delete to
                contained schemas and tables instead of rejecting with
                409 if the catalog is non-empty.
        """
        await _delete_catalog.asyncio(
            name=catalog_name, client=self._client, force=force
        )

    @_wrap_catalog_errors
    async def update_catalog(
        self, catalog_name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial update to a catalog.

        Args:
            catalog_name: Target catalog.
            patch: Fields to update, e.g. ``{"comment": "..."}``.

        Returns:
            The updated catalog object as returned by soyuz-catalog.
        """
        body = UpdateCatalog.from_dict(patch)
        response = await _update_catalog.asyncio(
            name=catalog_name, client=self._client, body=body
        )
        if response is None:
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def update_schema(
        self, catalog_name: str, schema_name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial update to a schema."""
        full_name = f"{catalog_name}.{schema_name}"
        body = UpdateSchema.from_dict(patch)
        response = await _update_schema.asyncio(
            full_name=full_name, client=self._client, body=body
        )
        if response is None:
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def get_tags(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        """Return tags for a securable (catalog, schema, or table).

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``.
            full_name: Dotted name of the securable.

        Returns:
            A list of tag dicts with ``key``, ``value``, timestamps.
        """
        st = GetTagsTagsSecurableTypeFullNameGetSecurableType(securable_type)
        response = await _get_tags.asyncio(
            securable_type=st, full_name=full_name, client=self._client
        )
        if not isinstance(response, TagList):
            return []
        tags = response.tags
        if not isinstance(tags, list):
            return []
        return [t.to_dict() for t in tags]

    @_wrap_catalog_errors
    async def update_tags(
        self,
        securable_type: str,
        full_name: str,
        changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply tag changes (set/remove) and return the updated tag list.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``.
            full_name: Dotted name of the securable.
            changes: List of ``{"key": ..., "op": "set"|"remove", "value": ...}``
                dicts.

        Returns:
            The updated tag list after applying changes.
        """
        st = UpdateTagsTagsSecurableTypeFullNamePatchSecurableType(securable_type)
        body = UpdateTags.from_dict({"changes": changes})
        response = await _update_tags.asyncio(
            securable_type=st,
            full_name=full_name,
            client=self._client,
            body=body,
        )
        if not isinstance(response, TagList):
            return []
        tags = response.tags
        if not isinstance(tags, list):
            return []
        return [t.to_dict() for t in tags]

    @_wrap_catalog_errors
    async def get_permissions(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        """Return privilege assignments for a securable.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.

        Returns:
            A list of privilege assignment dicts with ``principal`` and
            ``privileges``.
        """
        st = GetPermissionsApi21UnityCatalogPermissionsSecurableTypeFullNameGetSecurableType(
            securable_type
        )
        response = await _get_permissions.asyncio(
            securable_type=st, full_name=full_name, client=self._client
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]

    @_wrap_catalog_errors
    async def get_effective_permissions(
        self, securable_type: str, full_name: str
    ) -> list[dict[str, Any]]:
        """Return effective (inherited) permissions for a securable.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.

        Returns:
            A list of effective privilege assignment dicts.
        """
        _EffectiveType = GetEffectivePermissionsApi21UnityCatalogEffectivePermissionsSecurableTypeFullNameGetSecurableType  # noqa: E501, N806
        st = _EffectiveType(securable_type)
        response = await _get_effective_permissions.asyncio(
            securable_type=st, full_name=full_name, client=self._client
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]

    @_wrap_catalog_errors
    async def update_permissions(
        self,
        securable_type: str,
        full_name: str,
        changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply permission changes and return updated assignments.

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``, etc.
            full_name: Dotted name of the securable.
            changes: List of ``{"principal": ..., "add": [...], "remove": [...]}``
                dicts.

        Returns:
            The updated privilege assignment list.
        """
        st = UpdatePermissionsApi21UnityCatalogPermissionsSecurableTypeFullNamePatchSecurableType(
            securable_type
        )
        body = UpdatePermissions.from_dict({"changes": changes})
        response = await _update_permissions.asyncio(
            securable_type=st,
            full_name=full_name,
            client=self._client,
            body=body,
        )
        if not isinstance(response, PermissionsList):
            return []
        return [a.to_dict() for a in response.privilege_assignments]

    @_wrap_catalog_errors
    async def get_lineage(
        self, full_name: str, depth: int = 3
    ) -> dict[str, Any]:
        """Return combined upstream and downstream lineage for a table.

        Args:
            full_name: Three-part table name (catalog.schema.table).
            depth: How many hops to traverse (default 3).

        Returns:
            A dict with ``upstream`` and ``downstream`` keys, each
            containing ``nodes`` and ``edges`` lists (or empty dicts
            if no lineage data exists).
        """
        upstream_resp, downstream_resp = await asyncio.gather(
            _get_upstream.asyncio(
                full_name=full_name, client=self._client, depth=depth
            ),
            _get_downstream.asyncio(
                full_name=full_name, client=self._client, depth=depth
            ),
        )
        result: dict[str, Any] = {"upstream": {}, "downstream": {}}
        if isinstance(upstream_resp, LineageGraphResponse):
            result["upstream"] = upstream_resp.to_dict()
        if isinstance(downstream_resp, LineageGraphResponse):
            result["downstream"] = downstream_resp.to_dict()
        return result

    @_wrap_catalog_errors
    async def list_schemas(self, catalog_name: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Args:
            catalog_name: Name of the parent catalog.

        Returns:
            A list of schema dicts.
        """
        response = await _list_schemas.asyncio(
            client=self._client, catalog_name=catalog_name
        )
        if not isinstance(response, ListSchemasResponse):
            return []
        schemas = response.schemas
        if not isinstance(schemas, list):
            return []
        return [s.to_dict() for s in schemas]

    @_wrap_catalog_errors
    async def list_tables(
        self, catalog_name: str, schema_name: str
    ) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Bypasses the generated client's response parser because
        soyuz-catalog returns full ``TableInfo`` objects under a
        ``"tables"`` key whereas the generated model expects lightweight
        identifiers under ``"identifiers"`` — a spec mismatch to be
        fixed upstream.

        Args:
            catalog_name: Name of the parent catalog.
            schema_name: Name of the parent schema.

        Returns:
            A list of table dicts.
        """
        url = "/api/2.1/unity-catalog/tables"
        params = {"catalog_name": catalog_name, "schema_name": schema_name}
        http = self._client.get_async_httpx_client()
        resp = await http.get(url, params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("tables", data.get("identifiers", []))

    # -- Connections --

    @_wrap_catalog_errors
    async def list_connections(self) -> list[dict[str, Any]]:
        """Return all federation connections."""
        response = await _list_connections.asyncio(client=self._client)
        if not isinstance(response, ListConnectionsResponse):
            return []
        return [c.to_dict() for c in response.connections]

    @_wrap_catalog_errors
    async def get_connection(self, name: str) -> dict[str, Any]:
        """Return a single connection by name."""
        response = await _get_connection.asyncio(name=name, client=self._client)
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def create_connection(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new connection."""
        body = CreateConnection.from_dict(data)
        response = await _create_connection.asyncio(
            client=self._client, body=body
        )
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def update_connection(
        self, name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing connection."""
        body = UpdateConnection.from_dict(patch)
        response = await _update_connection.asyncio(
            name=name, client=self._client, body=body
        )
        if not isinstance(response, ConnectionInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def delete_connection(self, name: str) -> None:
        """Delete a connection."""
        await _delete_connection.asyncio(name=name, client=self._client)

    # -- External Locations --

    @_wrap_catalog_errors
    async def list_external_locations(self) -> list[dict[str, Any]]:
        """Return all external locations."""
        response = await _list_ext_locs.asyncio(client=self._client)
        if not isinstance(response, ListExternalLocationsResponse):
            return []
        return [e.to_dict() for e in response.external_locations]

    @_wrap_catalog_errors
    async def get_external_location(self, name: str) -> dict[str, Any]:
        """Return a single external location by name."""
        response = await _get_ext_loc.asyncio(name=name, client=self._client)
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def create_external_location(
        self, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new external location."""
        body = CreateExternalLocation.from_dict(data)
        response = await _create_ext_loc.asyncio(
            client=self._client, body=body
        )
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def update_external_location(
        self, name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing external location."""
        body = UpdateExternalLocation.from_dict(patch)
        response = await _update_ext_loc.asyncio(
            name=name, client=self._client, body=body
        )
        if not isinstance(response, ExternalLocationInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def delete_external_location(self, name: str) -> None:
        """Delete an external location."""
        await _delete_ext_loc.asyncio(name=name, client=self._client)

    # -- Credentials --

    @_wrap_catalog_errors
    async def list_credentials(self) -> list[dict[str, Any]]:
        """Return all credentials."""
        response = await _list_credentials.asyncio(client=self._client)
        if not isinstance(response, ListCredentialsResponse):
            return []
        return [c.to_dict() for c in response.credentials]

    @_wrap_catalog_errors
    async def get_credential(self, name: str) -> dict[str, Any]:
        """Return a single credential by name."""
        response = await _get_credential.asyncio(name=name, client=self._client)
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def create_credential(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new credential."""
        body = CreateCredentialRequest.from_dict(data)
        response = await _create_credential.asyncio(
            client=self._client, body=body
        )
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def update_credential(
        self, name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing credential."""
        body = UpdateCredentialRequest.from_dict(patch)
        response = await _update_credential.asyncio(
            name=name, client=self._client, body=body
        )
        if not isinstance(response, CredentialInfo):
            return {}
        return response.to_dict()

    @_wrap_catalog_errors
    async def delete_credential(self, name: str) -> None:
        """Delete a credential."""
        await _delete_credential.asyncio(name=name, client=self._client)

    @_wrap_catalog_errors
    async def get_tree(self) -> list[dict[str, Any]]:
        """Return the full catalog tree in one shot.

        Fetches all catalogs, then all schemas per catalog, then all tables
        per schema concurrently. Intended for sidebar rendering where the
        whole tree is needed up-front.

        Returns:
            A list of catalogs, each enriched with a ``schemas`` key whose
            entries each carry a ``tables`` key.
        """
        catalogs = await self.list_catalogs()

        async def _with_schemas(cat: dict[str, Any]) -> dict[str, Any]:
            schemas = await self.list_schemas(cat["name"])

            async def _with_tables(schema: dict[str, Any]) -> dict[str, Any]:
                tables = await self.list_tables(cat["name"], schema["name"])
                return {**schema, "tables": tables}

            schema_results = await asyncio.gather(
                *(_with_tables(s) for s in schemas)
            )
            return {**cat, "schemas": list(schema_results)}

        return list(await asyncio.gather(*(_with_schemas(c) for c in catalogs)))
