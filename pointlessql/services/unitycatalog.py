"""Async wrapper around the generated soyuz-catalog client.

Delegates every HTTP call to the typed functions shipped with
``soyuz_catalog_client`` and converts the attrs response objects back
to plain dicts so that FastAPI routes and Jinja2 templates can consume
them without changes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.api.catalogs import (
    get_catalog_api_2_1_unity_catalog_catalogs_name_get as _get_catalog,
)
from soyuz_catalog_client.api.catalogs import (
    list_catalogs_api_2_1_unity_catalog_catalogs_get as _list_catalogs,
)
from soyuz_catalog_client.api.catalogs import (
    update_catalog_api_2_1_unity_catalog_catalogs_name_patch as _update_catalog,
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
from soyuz_catalog_client.api.tables import (
    list_tables_api_2_1_unity_catalog_tables_get as _list_tables,
)
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.list_tables_response import ListTablesResponse
from soyuz_catalog_client.models.update_catalog import UpdateCatalog
from soyuz_catalog_client.models.update_schema import UpdateSchema


class UnityCatalogClient:
    """Async facade over the generated soyuz-catalog client."""

    def __init__(self, client: Client) -> None:
        """Initialize the wrapper.

        Args:
            client: A configured ``soyuz_catalog_client.Client`` instance,
                typically built by :func:`pointlessql.services.soyuz_client.make_soyuz_client`.
        """
        self._client = client

    async def aclose(self) -> None:
        """Release the underlying HTTP resources."""
        await self._client.__aexit__()

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

    async def get_catalog(self, catalog_name: str) -> dict[str, Any]:
        """Return metadata for a single catalog."""
        response = await _get_catalog.asyncio(name=catalog_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    async def get_schema(
        self, catalog_name: str, schema_name: str
    ) -> dict[str, Any]:
        """Return metadata for a single schema."""
        full_name = f"{catalog_name}.{schema_name}"
        response = await _get_schema.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    async def get_table(
        self, catalog_name: str, schema_name: str, table_name: str
    ) -> dict[str, Any]:
        """Return metadata (including columns) for a single table."""
        full_name = f"{catalog_name}.{schema_name}.{table_name}"
        response = await _get_table.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

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

    async def list_tables(
        self, catalog_name: str, schema_name: str
    ) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Args:
            catalog_name: Name of the parent catalog.
            schema_name: Name of the parent schema.

        Returns:
            A list of table dicts.
        """
        response = await _list_tables.asyncio(
            client=self._client,
            catalog_name=catalog_name,
            schema_name=schema_name,
        )
        if not isinstance(response, ListTablesResponse):
            return []
        identifiers = response.identifiers
        if not isinstance(identifiers, list):
            return []
        return [t.to_dict() for t in identifiers]

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
