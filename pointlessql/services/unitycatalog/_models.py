"""Registered-model + model-version CRUD (Phase 21.5).

Wraps the typed soyuz client functions for the UC-OSS MODEL Securable.
RegisteredModels and ModelVersions land in soyuz via Sprint 21.1; this
mixin exposes them through ``UnityCatalogClient`` so PointlesSQL UI
routes can treat them like tables and schemas.
"""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.api.model_versions import (
    get_model_version_api_2_1_unity_catalog_models_full_name_versions_version_get as _get_mv,
)
from soyuz_catalog_client.api.model_versions import (
    list_model_versions_api_2_1_unity_catalog_models_full_name_versions_get as _list_mv,
)
from soyuz_catalog_client.api.registered_models import (
    get_registered_model_api_2_1_unity_catalog_models_full_name_get as _get_rm,
)
from soyuz_catalog_client.api.registered_models import (
    list_registered_models_api_2_1_unity_catalog_models_get as _list_rm,
)
from soyuz_catalog_client.api.registered_models import (
    update_registered_model_api_2_1_unity_catalog_models_full_name_patch as _update_rm,
)
from soyuz_catalog_client.models.list_model_versions_response import (
    ListModelVersionsResponse,
)
from soyuz_catalog_client.models.list_registered_models_response import (
    ListRegisteredModelsResponse,
)
from soyuz_catalog_client.models.update_registered_model import UpdateRegisteredModel

from pointlessql.services.unitycatalog._api import wrap_catalog_errors


class ModelsMixin:
    """Registered-model + model-version operations."""

    _client: Client  # provided by UnityCatalogClient

    @wrap_catalog_errors
    async def list_registered_models(
        self,
        catalog_name: str | None = None,
        schema_name: str | None = None,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return registered models, optionally scoped to a catalog/schema.

        Args:
            catalog_name: Optional parent catalog filter.
            schema_name: Optional parent schema filter (requires
                ``catalog_name`` per UC-OSS spec).
            max_results: Page size hint, 1..1000.
            page_token: Opaque cursor from a previous response.

        Returns:
            A list of registered-model dicts. Empty list when soyuz
            reports no rows.
        """
        kwargs: dict[str, Any] = {"client": self._client}
        if catalog_name is not None:
            kwargs["catalog_name"] = catalog_name
        if schema_name is not None:
            kwargs["schema_name"] = schema_name
        if max_results is not None:
            kwargs["max_results"] = max_results
        if page_token is not None:
            kwargs["page_token"] = page_token
        response = await _list_rm.asyncio(**kwargs)
        if not isinstance(response, ListRegisteredModelsResponse):
            return []
        models = response.registered_models
        if not isinstance(models, list):
            return []
        return [m.to_dict() for m in models]

    @wrap_catalog_errors
    async def get_registered_model(self, full_name: str) -> dict[str, Any]:
        """Return metadata for a single registered model."""
        response = await _get_rm.asyncio(full_name=full_name, client=self._client)
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def list_model_versions(
        self,
        full_name: str,
        max_results: int | None = None,
        page_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all versions for a registered model.

        Args:
            full_name: Three-level FQN ``catalog.schema.model``.
            max_results: Page size hint, 1..1000.
            page_token: Opaque cursor from a previous response.

        Returns:
            A list of model-version dicts.
        """
        kwargs: dict[str, Any] = {"full_name": full_name, "client": self._client}
        if max_results is not None:
            kwargs["max_results"] = max_results
        if page_token is not None:
            kwargs["page_token"] = page_token
        response = await _list_mv.asyncio(**kwargs)
        if not isinstance(response, ListModelVersionsResponse):
            return []
        versions = response.model_versions
        if not isinstance(versions, list):
            return []
        return [v.to_dict() for v in versions]

    @wrap_catalog_errors
    async def get_model_version(self, full_name: str, version: int) -> dict[str, Any]:
        """Return metadata for a single model version."""
        response = await _get_mv.asyncio(
            full_name=full_name, version=version, client=self._client
        )
        if response is None:
            return {}
        return response.to_dict()

    @wrap_catalog_errors
    async def update_registered_model(
        self,
        full_name: str,
        comment: str | None = None,
        new_name: str | None = None,
    ) -> dict[str, Any]:
        """Patch a registered model's mutable fields.

        UC-OSS spec only permits ``comment`` and ``new_name``; passing
        anything else server-side is rejected with HTTP 422. Sprint
        21.6 uses this to write the ``_pql_promotion`` JSON marker
        into the comment field.

        Args:
            full_name: Three-level FQN ``catalog.schema.model``.
            comment: New comment value, or ``None`` to leave untouched.
            new_name: New short name, or ``None`` to leave untouched.

        Returns:
            The updated registered-model dict, or an empty dict when
            soyuz returned no body.
        """
        body = UpdateRegisteredModel()
        if comment is not None:
            body.comment = comment
        if new_name is not None:
            body.new_name = new_name
        response = await _update_rm.asyncio(
            full_name=full_name, client=self._client, body=body
        )
        if response is None:
            return {}
        return response.to_dict()
