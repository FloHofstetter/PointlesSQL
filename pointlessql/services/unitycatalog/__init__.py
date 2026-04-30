"""Async wrapper around the generated soyuz-catalog client.

Delegates every HTTP call to the typed functions shipped with
``soyuz_catalog_client`` and converts the attrs response objects back
to plain dicts so that FastAPI routes and Jinja2 templates can consume
them without changes.

The package is composed of six sibling modules under
``services/unitycatalog/``:

* :mod:`._api` — every typed soyuz function imported as
  ``_get_X`` / ``_create_X`` / ``_update_X`` / ``_delete_X`` /
  ``_list_X`` (the names tests still patch by string), plus the
  shared :func:`wrap_catalog_errors` decorator.
* :mod:`._catalogs` — :class:`CatalogsMixin` (catalog CRUD + bulk
  ``get_tree`` aggregator that calls back into the metadata mixin).
* :mod:`._metadata` — :class:`MetadataMixin` (schema + table + tag
  CRUD).
* :mod:`._permissions` — :class:`PermissionsMixin` (direct + effective
  permissions).
* :mod:`._lineage` — :class:`LineageMixin` (upstream + downstream).
* :mod:`._federation` — :class:`FederationMixin` (connections +
  external locations + credentials).

The concrete :class:`UnityCatalogClient` composes the mixins.  Because
the soyuz function imports are re-exported at the legacy
``pointlessql.services.unitycatalog._XYZ`` paths, existing tests that
do ``patch("pointlessql.services.unitycatalog._get_tags.asyncio")``
keep finding the same module object the mixin will call into.
"""

from __future__ import annotations

from soyuz_catalog_client import Client

# Re-export the soyuz function bindings + the error decorator at the
# legacy module path so test patches and any external code that
# referenced them stay resolvable.  Mixins import these from
# ``._api`` directly (one source of truth for the binding).
from pointlessql.services.unitycatalog._api import (
    _create_catalog,
    _create_connection,
    _create_credential,
    _create_ext_loc,
    _create_schema,
    _create_table,
    _delete_catalog,
    _delete_connection,
    _delete_credential,
    _delete_ext_loc,
    _delete_schema,
    _delete_table,
    _get_catalog,
    _get_connection,
    _get_credential,
    _get_downstream,
    _get_effective_permissions,
    _get_ext_loc,
    _get_permissions,
    _get_schema,
    _get_table,
    _get_tags,
    _get_upstream,
    _list_catalogs,
    _list_connections,
    _list_credentials,
    _list_ext_locs,
    _list_schemas,
    _update_catalog,
    _update_connection,
    _update_credential,
    _update_ext_loc,
    _update_permissions,
    _update_schema,
    _update_tags,
    wrap_catalog_errors,
)
from pointlessql.services.unitycatalog._catalogs import CatalogsMixin
from pointlessql.services.unitycatalog._federation import FederationMixin
from pointlessql.services.unitycatalog._lineage import LineageMixin
from pointlessql.services.unitycatalog._metadata import MetadataMixin
from pointlessql.services.unitycatalog._models import ModelsMixin
from pointlessql.services.unitycatalog._permissions import PermissionsMixin


class UnityCatalogClient(
    CatalogsMixin,
    MetadataMixin,
    ModelsMixin,
    PermissionsMixin,
    LineageMixin,
    FederationMixin,
):
    """Async facade over the generated soyuz-catalog client.

    Composes per-securable mixins (catalogs, metadata, permissions,
    lineage, federation) into a single client surface.

    Args:
        client: A configured ``soyuz_catalog_client.Client`` instance,
            typically built by
            :func:`pointlessql.services.soyuz_client.make_soyuz_client`.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    def for_principal(cls, settings: object, principal: str) -> UnityCatalogClient:
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


__all__ = [
    "CatalogsMixin",
    "FederationMixin",
    "LineageMixin",
    "MetadataMixin",
    "ModelsMixin",
    "PermissionsMixin",
    "UnityCatalogClient",
    "_create_catalog",
    "_create_connection",
    "_create_credential",
    "_create_ext_loc",
    "_create_schema",
    "_create_table",
    "_delete_catalog",
    "_delete_connection",
    "_delete_credential",
    "_delete_ext_loc",
    "_delete_schema",
    "_delete_table",
    "_get_catalog",
    "_get_connection",
    "_get_credential",
    "_get_downstream",
    "_get_effective_permissions",
    "_get_ext_loc",
    "_get_permissions",
    "_get_schema",
    "_get_table",
    "_get_tags",
    "_get_upstream",
    "_list_catalogs",
    "_list_connections",
    "_list_credentials",
    "_list_ext_locs",
    "_list_schemas",
    "_update_catalog",
    "_update_connection",
    "_update_credential",
    "_update_ext_loc",
    "_update_permissions",
    "_update_schema",
    "_update_tags",
    "wrap_catalog_errors",
]
