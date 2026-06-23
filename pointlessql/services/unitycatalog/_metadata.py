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
from pointlessql.types import TableFqn

# Upper bound on pages drained per list call — a backstop against a
# provider that returns a self-referential next_page_token forever.
_MAX_LIST_PAGES = 1000


class MetadataMixin:
    """Schema + table + tag operations.

    The metadata-browsing core: schemas and tables under a catalog,
    plus the tag edges hung off any securable. Several list methods
    page directly against soyuz endpoints the generated client does
    not yet wrap.

    Every method routes through ``@wrap_catalog_errors``, which normalises
    soyuz-catalog failures into domain exceptions (the shared error
    mapping): a 404 becomes ``CatalogNotFoundError``, other 4xx and
    malformed request bodies become ``ValidationError``, and 5xx /
    transport errors become ``CatalogUnavailableError``.
    """

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def get_schema(self, catalog_name: str, schema_name: str) -> dict[str, Any]:
        """Return metadata for a single schema.

        Failures are normalised by the shared error mapping (see the
        class docstring): an unknown schema surfaces as
        ``CatalogNotFoundError``.

        Args:
            catalog_name: Parent catalog.
            schema_name: Target schema.

        Returns:
            The schema's fields as a dict, or ``{}`` if soyuz returned
            no parsed body.
        """
        full_name = f"{catalog_name}.{schema_name}"
        response = await _get_schema.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def get_table(
        self, catalog_name: str, schema_name: str, table_name: str
    ) -> dict[str, Any]:
        """Return metadata, including columns, for a single table.

        Failures are normalised by the shared error mapping (see the
        class docstring): an unknown table surfaces as
        ``CatalogNotFoundError``.

        Args:
            catalog_name: Parent catalog.
            schema_name: Parent schema.
            table_name: Target table.

        Returns:
            The table's fields as a dict, or ``{}`` if soyuz returned no
            parsed body.
        """
        full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
        response = await _get_table.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new schema under an existing catalog.

        Failures are normalised by the shared error mapping (see the
        class docstring); a body that ``CreateSchema.from_dict`` cannot
        parse surfaces as ``ValidationError``.

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

        Failures are normalised by the shared error mapping (see the
        class docstring); a partial or unparseable body surfaces as
        ``ValidationError``.

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
        disappeared from the source database. Failures are normalised by
        the shared error mapping (see the class docstring).

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

        Failures are normalised by the shared error mapping (see the
        class docstring).

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
        """Apply a partial update to a schema.

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            catalog_name: Parent catalog.
            schema_name: Target schema.
            patch: Partial body matching ``UpdateSchema``.

        Returns:
            The updated schema as a dict, or ``{}`` if soyuz returned no
            parsed body.
        """
        full_name = f"{catalog_name}.{schema_name}"
        body = UpdateSchema.from_dict(patch)
        response = await _update_schema.asyncio(full_name=full_name, client=self._client, body=body)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def list_schemas(self, catalog_name: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Drains every page (capped at ``_MAX_LIST_PAGES``) and stops
        early if soyuz returns an unexpected response shape. Failures
        are normalised by the shared error mapping (see the class
        docstring).

        Args:
            catalog_name: Name of the parent catalog.

        Returns:
            A list of schema dicts, or ``[]`` if soyuz returned an
            unexpected response shape on the first page.
        """
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_MAX_LIST_PAGES):
            response = await _list_schemas.asyncio(
                client=self._client, catalog_name=catalog_name, page_token=page_token
            )
            if not isinstance(response, ListSchemasResponse):
                break
            schemas = response.schemas
            if isinstance(schemas, list):
                out.extend(s.to_dict() for s in schemas)
            next_token = response.next_page_token
            if not isinstance(next_token, str) or not next_token:
                break
            page_token = next_token
        return out

    @wrap_catalog_errors
    async def list_tables(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Bypasses the generated client's response parser because
        soyuz-catalog returns full ``TableInfo`` objects under a
        ``"tables"`` key whereas the generated model expects lightweight
        identifiers under ``"identifiers"`` — a spec mismatch to be
        fixed upstream.

        A 404 is treated as "no tables" and yields ``[]``; any other
        non-2xx surfaces through the shared error mapping (see the class
        docstring) so the tree shows "unavailable" rather than an empty
        schema.

        Args:
            catalog_name: Name of the parent catalog.
            schema_name: Name of the parent schema.

        Returns:
            A list of table dicts, or ``[]`` when the schema has no
            tables.
        """
        url = "/api/2.1/unity-catalog/tables"
        http = self._client.get_async_httpx_client()
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_MAX_LIST_PAGES):
            params = {"catalog_name": catalog_name, "schema_name": schema_name}
            if page_token:
                params["page_token"] = page_token
            resp = await http.get(url, params=params)
            # 404 means the schema genuinely has no tables endpoint; any
            # other error (5xx, timeout) must surface so the tree shows
            # "unavailable" rather than silently rendering an empty schema.
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            data = resp.json()
            out.extend(data.get("tables", data.get("identifiers", [])))
            next_token = data.get("next_page_token")
            if not next_token:
                break
            page_token = next_token
        return out

    @wrap_catalog_errors
    async def list_volumes(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        """Return all volumes inside a schema.

        Calls the soyuz ``/api/2.1/unity-catalog/volumes`` endpoint
        directly because the generated client does not yet wrap it.
        Same shape as :meth:`list_tables` so :meth:`get_tree` can
        treat volumes as a third sibling list alongside tables +
        models. A 404 yields ``[]``; any other non-2xx surfaces through
        the shared error mapping (see the class docstring).

        Args:
            catalog_name: Name of the parent catalog.
            schema_name: Name of the parent schema.

        Returns:
            A list of volume dicts, or ``[]`` when the schema has no
            volumes.
        """
        url = "/api/2.1/unity-catalog/volumes"
        http = self._client.get_async_httpx_client()
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_MAX_LIST_PAGES):
            params = {"catalog_name": catalog_name, "schema_name": schema_name}
            if page_token:
                params["page_token"] = page_token
            resp = await http.get(url, params=params)
            # 404 → genuinely absent; surface everything else as unavailable.
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            data = resp.json()
            out.extend(data.get("volumes", []))
            next_token = data.get("next_page_token")
            if not next_token:
                break
            page_token = next_token
        return out

    @wrap_catalog_errors
    async def get_tags(self, securable_type: str, full_name: str) -> list[dict[str, Any]]:
        """Return tags for a securable (catalog, schema, or table).

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``.
            full_name: Dotted name of the securable.

        Returns:
            A list of tag dicts with ``key``, ``value``, timestamps, or
            ``[]`` if soyuz returned an unexpected response shape.
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

        Failures are normalised by the shared error mapping (see the
        class docstring).

        Args:
            securable_type: One of ``catalog``, ``schema``, ``table``.
            full_name: Dotted name of the securable.
            changes: List of ``{"key": ..., "op": "set"|"remove", "value": ...}``
                dicts.

        Returns:
            The updated tag list after applying changes, or ``[]`` if
            soyuz returned an unexpected response shape.
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
