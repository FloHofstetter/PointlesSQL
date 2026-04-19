"""Upstream + downstream lineage walks."""

from __future__ import annotations

import asyncio
from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.lineage_graph_response import LineageGraphResponse

from pointlessql.services.unitycatalog._api import (
    _get_downstream,
    _get_upstream,
    wrap_catalog_errors,
)


class LineageMixin:
    """Combined upstream + downstream lineage for a table."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def get_lineage(self, full_name: str, depth: int = 3) -> dict[str, Any]:
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
            _get_upstream.asyncio(full_name=full_name, client=self._client, depth=depth),
            _get_downstream.asyncio(full_name=full_name, client=self._client, depth=depth),
        )
        result: dict[str, Any] = {"upstream": {}, "downstream": {}}
        if isinstance(upstream_resp, LineageGraphResponse):
            result["upstream"] = upstream_resp.to_dict()
        if isinstance(downstream_resp, LineageGraphResponse):
            result["downstream"] = downstream_resp.to_dict()
        return result
