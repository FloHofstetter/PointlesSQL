"""Catalog CRUD + the cross-mixin ``get_tree`` aggregator."""

from __future__ import annotations

import asyncio
from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.catalog_info import CatalogInfo
from soyuz_catalog_client.models.create_catalog import CreateCatalog
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.update_catalog import UpdateCatalog

from pointlessql.services.unitycatalog._api import (
    _create_catalog,
    _delete_catalog,
    _get_catalog,
    _list_catalogs,
    _update_catalog,
    wrap_catalog_errors,
)


class CatalogsMixin:
    """Catalog-level CRUD + the bulk-tree aggregator."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
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

    @wrap_catalog_errors
    async def get_catalog(self, catalog_name: str) -> dict[str, Any]:
        """Return metadata for a single catalog."""
        response = await _get_catalog.asyncio(name=catalog_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_catalog(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new catalog (managed or foreign).

        Foreign catalogs are a soyuz-catalog variant: pass
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

    @wrap_catalog_errors
    async def delete_catalog(self, catalog_name: str, force: bool = False) -> None:
        """Delete a catalog.

        Args:
            catalog_name: Target catalog.
            force: When ``True``, soyuz-catalog cascades the delete to
                contained schemas and tables instead of rejecting with
                409 if the catalog is non-empty.
        """
        await _delete_catalog.asyncio(name=catalog_name, client=self._client, force=force)

    @wrap_catalog_errors
    async def update_catalog(self, catalog_name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update to a catalog.

        Args:
            catalog_name: Target catalog.
            patch: Fields to update, e.g. ``{"comment": "..."}``.

        Returns:
            The updated catalog object as returned by soyuz-catalog.
        """
        body = UpdateCatalog.from_dict(patch)
        response = await _update_catalog.asyncio(name=catalog_name, client=self._client, body=body)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def get_tree(self) -> list[dict[str, Any]]:
        """Return the full catalog tree in one shot.

        Fetches all catalogs, then all schemas per catalog, then all
        tables + registered-models per schema concurrently.  Intended
        for sidebar rendering where the whole tree is needed up-front.
        Cross-mixin: relies on :meth:`MetadataMixin.list_schemas`,
        :meth:`MetadataMixin.list_tables`, and
        :meth:`ModelsMixin.list_registered_models` being on ``self``
        via the concrete :class:`UnityCatalogClient`.

        Returns:
            A list of catalogs, each enriched with a ``schemas`` key
            whose entries each carry both ``tables`` and ``models``
            keys.
        """
        catalogs = await self.list_catalogs()

        async def _with_schemas(cat: dict[str, Any]) -> dict[str, Any]:
            schemas = await self.list_schemas(cat["name"])  # type: ignore[attr-defined]

            async def _with_children(schema: dict[str, Any]) -> dict[str, Any]:
                tables_task = self.list_tables(cat["name"], schema["name"])  # type: ignore[attr-defined]
                models_task = self.list_registered_models(  # type: ignore[attr-defined]
                    catalog_name=cat["name"], schema_name=schema["name"]
                )
                tables, models = await asyncio.gather(tables_task, models_task)
                return {**schema, "tables": tables, "models": models}

            schema_results = await asyncio.gather(*(_with_children(s) for s in schemas))
            return {**cat, "schemas": list(schema_results)}

        return list(await asyncio.gather(*(_with_schemas(c) for c in catalogs)))
