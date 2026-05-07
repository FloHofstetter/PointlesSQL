"""Schema + Table + Tag CRUD."""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.create_schema import CreateSchema
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.get_tags_tags_securable_type_full_name_get_securable_type import (
    GetTagsTagsSecurableTypeFullNameGetSecurableType,
)
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.tag_list import TagList
from soyuz_catalog_client.models.update_schema import UpdateSchema
from soyuz_catalog_client.models.update_tags import UpdateTags
from soyuz_catalog_client.models.update_tags_tags_securable_type_full_name_patch_securable_type import (  # noqa: E501
    UpdateTagsTagsSecurableTypeFullNamePatchSecurableType,
)

from pointlessql.services.unitycatalog._api import (
    _create_schema,
    _create_table,
    _delete_schema,
    _delete_table,
    _get_schema,
    _get_table,
    _get_tags,
    _list_schemas,
    _update_schema,
    _update_tags,
    wrap_catalog_errors,
)
from pointlessql.table_fqn import TableFqn


class MetadataMixin:
    """Schema + table + tag operations."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def get_schema(self, catalog_name: str, schema_name: str) -> dict[str, Any]:
        """Return metadata for a single schema."""
        full_name = f"{catalog_name}.{schema_name}"
        response = await _get_schema.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def get_table(
        self, catalog_name: str, schema_name: str, table_name: str
    ) -> dict[str, Any]:
        """Return metadata (including columns) for a single table."""
        full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
        response = await _get_table.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new schema under an existing catalog.

        Args:
            data: Request body matching ``CreateSchema`` — requires
                ``catalog_name`` and ``name``; ``storage_root`` is
                optional on managed parents and ignored on foreign
                parents (soyuz rejects it there at the service layer).

        Returns:
            The created schema as returned by soyuz-catalog, or an
            empty dict when the server returned no parsed body.
        """
        from soyuz_catalog_client.models.schema_info import SchemaInfo

        body = CreateSchema.from_dict(data)
        response = await _create_schema.asyncio(client=self._client, body=body)
        if not isinstance(response, SchemaInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_table(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new table under an existing schema.

        Used by the Postgres sync worker to mirror foreign-catalog
        tables. Every field listed as required in the UC spec
        (``name``, ``catalog_name``, ``schema_name``, ``table_type``,
        ``data_source_format``, ``columns``, ``storage_location``) must
        be present — soyuz rejects partial payloads with 422.

        Args:
            data: Request body matching ``CreateTable``.

        Returns:
            The created table as returned by soyuz-catalog, or an empty
            dict when the server returned no parsed body.
        """
        from soyuz_catalog_client.models.table_info import TableInfo

        body = CreateTable.from_dict(data)
        response = await _create_table.asyncio(client=self._client, body=body)
        if not isinstance(response, TableInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_table(self, catalog_name: str, schema_name: str, table_name: str) -> None:
        """Delete a table by its three-part name.

        Used by the Postgres sync worker to drop tables that have
        disappeared from the source database.

        Args:
            catalog_name: Parent catalog.
            schema_name: Parent schema.
            table_name: Target table.
        """
        full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
        await _delete_table.asyncio(full_name=full_name, client=self._client)

    @wrap_catalog_errors
    async def delete_schema(
        self,
        catalog_name: str,
        schema_name: str,
        *,
        force: bool = False,
    ) -> None:
        """Delete a schema by its two-part name.

        Used by the  branch-discard primitive to drop the
        UC namespace once the branch's per-table storage has been
        removed.  ``force=True`` lets soyuz cascade-delete any
        remaining tables in the schema; the discard primitive cleans
        them explicitly first, so ``force=False`` is the default.

        Args:
            catalog_name: Parent catalog.
            schema_name: Target schema.
            force: When ``True``, soyuz cascade-deletes nested tables.
        """
        full_name = f"{catalog_name}.{schema_name}"
        await _delete_schema.asyncio(
            full_name=full_name,
            client=self._client,
            force=force,
        )

    @wrap_catalog_errors
    async def update_schema(
        self, catalog_name: str, schema_name: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial update to a schema."""
        full_name = f"{catalog_name}.{schema_name}"
        body = UpdateSchema.from_dict(patch)
        response = await _update_schema.asyncio(full_name=full_name, client=self._client, body=body)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def list_schemas(self, catalog_name: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Args:
            catalog_name: Name of the parent catalog.

        Returns:
            A list of schema dicts.
        """
        response = await _list_schemas.asyncio(client=self._client, catalog_name=catalog_name)
        if not isinstance(response, ListSchemasResponse):
            return []
        schemas = response.schemas
        if not isinstance(schemas, list):
            return []
        return [s.to_dict() for s in schemas]

    @wrap_catalog_errors
    async def list_tables(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
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

    @wrap_catalog_errors
    async def list_volumes(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        """Return all volumes inside a schema.

        Calls the soyuz ``/api/2.1/unity-catalog/volumes`` endpoint
        directly because the generated client does not yet wrap it.
        Same shape as :meth:`list_tables` so :meth:`get_tree` can
        treat volumes as a third sibling list alongside tables +
        models.

        Args:
            catalog_name: Name of the parent catalog.
            schema_name: Name of the parent schema.

        Returns:
            A list of volume dicts.
        """
        url = "/api/2.1/unity-catalog/volumes"
        params = {"catalog_name": catalog_name, "schema_name": schema_name}
        http = self._client.get_async_httpx_client()
        resp = await http.get(url, params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("volumes", [])

    @wrap_catalog_errors
    async def get_tags(self, securable_type: str, full_name: str) -> list[dict[str, Any]]:
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

    @wrap_catalog_errors
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
