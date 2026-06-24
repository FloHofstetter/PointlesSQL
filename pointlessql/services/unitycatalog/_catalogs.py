"""Catalog CRUD + the cross-mixin ``get_tree`` aggregator."""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)

# Upper bound on pages drained per list call — a backstop against a
# provider that returns a self-referential next_page_token forever.
_MAX_LIST_PAGES = 1000


class CatalogsMixin:
    """Catalog-level CRUD + the bulk-tree aggregator."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def list_catalogs(self) -> list[dict[str, Any]]:
        """Return all catalogs visible to the caller.

        Follows ``next_page_token`` to the end so a large install is not
        silently truncated to soyuz's first page.

        Returns:
            A list of catalog dicts, or an empty list if the server
            reports none.
        """
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(_MAX_LIST_PAGES):
            response = await _list_catalogs.asyncio(client=self._client, page_token=page_token)
            if not isinstance(response, ListCatalogsResponse):
                break
            catalogs = response.catalogs
            if isinstance(catalogs, list):
                out.extend(c.to_dict() for c in catalogs)
            next_token = response.next_page_token
            if not isinstance(next_token, str) or not next_token:
                break
            page_token = next_token
        return out

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
        tables + volumes + registered-models per schema concurrently.
        Intended for sidebar rendering where the whole tree is needed
        up-front.  Cross-mixin: relies on
        :meth:`MetadataMixin.list_schemas`,
        :meth:`MetadataMixin.list_tables`,
        :meth:`MetadataMixin.list_volumes`, and
        :meth:`ModelsMixin.list_registered_models` being on ``self``
        via the concrete :class:`UnityCatalogClient`.

        Returns:
            A list of catalogs, each enriched with a ``schemas`` key
            whose entries each carry ``tables``, ``volumes``, and
            ``models`` keys.
        """
        from pointlessql.config import get_settings

        catalogs = await self.list_catalogs()
        # Bound the per-schema child fan-out so a wide catalog cannot
        # stampede soyuz with thousands of concurrent GETs.
        semaphore = asyncio.Semaphore(max(1, get_settings().soyuz.tree_fanout_concurrency))

        async def _with_schemas(cat: dict[str, Any]) -> dict[str, Any]:
            schemas = await self.list_schemas(cat["name"])  # type: ignore[attr-defined]

            async def _with_children(schema: dict[str, Any]) -> dict[str, Any]:
                async with semaphore:
                    try:
                        tables, volumes, models = await asyncio.gather(
                            self.list_tables(cat["name"], schema["name"]),  # type: ignore[attr-defined]
                            self.list_volumes(cat["name"], schema["name"]),  # type: ignore[attr-defined]
                            self.list_registered_models(  # type: ignore[attr-defined]
                                catalog_name=cat["name"], schema_name=schema["name"]
                            ),
                        )
                    except Exception:  # noqa: BLE001 — degrade one schema, not the tree
                        # A failing/unavailable schema must not abort the whole
                        # sidebar render — surface it as an empty, partial node.
                        logger.warning(
                            "get_tree: children fetch failed for %s.%s",
                            cat["name"],
                            schema["name"],
                            exc_info=True,
                        )
                        return {
                            **schema,
                            "tables": [],
                            "volumes": [],
                            "models": [],
                            "partial": True,
                        }
                return {
                    **schema,
                    "tables": tables,
                    "volumes": volumes,
                    "models": models,
                }

            schema_results = await asyncio.gather(*(_with_children(s) for s in schemas))
            return {**cat, "schemas": list(schema_results)}

        return list(await asyncio.gather(*(_with_schemas(c) for c in catalogs)))
