"""Semantic-layer surface: metric-view definition CRUD.

soyuz-catalog stores the definitions (dimension / measure exprs are
opaque strings there); compiling them into executable SQL is
PointlesSQL's job (:mod:`pointlessql.pql._metrics`).
"""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.models.create_metric_view import CreateMetricView
from soyuz_catalog_client.models.list_metric_views_response import (
    ListMetricViewsResponse,
)
from soyuz_catalog_client.models.metric_view_info import MetricViewInfo
from soyuz_catalog_client.models.update_metric_view import UpdateMetricView

from pointlessql.services.unitycatalog._api import (
    _create_metric_view,
    _delete_metric_view,
    _get_metric_view,
    _list_metric_views,
    _update_metric_view,
    wrap_catalog_errors,
)


class MetricViewsMixin:
    """Metric-view definition CRUD against soyuz-catalog."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def list_metric_views(self, catalog_name: str, schema_name: str) -> list[dict[str, Any]]:
        """Return the schema's metric views.

        Args:
            catalog_name: Parent catalog.
            schema_name: Parent schema.

        Returns:
            Metric-view info dicts (possibly empty).
        """
        response = await _list_metric_views.asyncio(
            client=self._client,
            catalog_name=catalog_name,
            schema_name=schema_name,
        )
        if not isinstance(response, ListMetricViewsResponse):
            return []
        return [view.to_dict() for view in response.metric_views]

    @wrap_catalog_errors
    async def get_metric_view(self, full_name: str) -> dict[str, Any]:
        """Return one metric view by ``catalog.schema.name``."""
        response = await _get_metric_view.asyncio(full_name=full_name, client=self._client)
        if not isinstance(response, MetricViewInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def create_metric_view(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a metric view from a request dict."""
        body = CreateMetricView.from_dict(data)
        response = await _create_metric_view.asyncio(client=self._client, body=body)
        if not isinstance(response, MetricViewInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_metric_view(self, full_name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch a metric view (spec / comment / source / rename)."""
        body = UpdateMetricView.from_dict(patch)
        response = await _update_metric_view.asyncio(
            full_name=full_name, client=self._client, body=body
        )
        if not isinstance(response, MetricViewInfo):
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def delete_metric_view(self, full_name: str) -> None:
        """Delete a metric view."""
        await _delete_metric_view.asyncio(full_name=full_name, client=self._client)
