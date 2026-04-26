"""Convenience listing helpers for :class:`PQL`."""

from __future__ import annotations

from typing import Any

from soyuz_catalog_client import Client
from soyuz_catalog_client.api.catalogs import (
    list_catalogs_api_2_1_unity_catalog_catalogs_get as _list_catalogs,
)
from soyuz_catalog_client.api.schemas import (
    list_schemas_api_2_1_unity_catalog_schemas_get as _list_schemas,
)
from soyuz_catalog_client.api.tables import (
    list_tables_api_2_1_unity_catalog_tables_get as _list_tables,
)
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.list_tables_response import ListTablesResponse


def list_catalogs(client: Client) -> list[dict[str, Any]]:
    """Return all catalogs visible to the caller.

    Args:
        client: Configured catalog client.

    Returns:
        A list of catalog dicts with at least a ``"name"`` key.
    """
    response = _list_catalogs.sync(client=client)
    if not isinstance(response, ListCatalogsResponse):
        return []
    catalogs = response.catalogs
    if not isinstance(catalogs, list):
        return []
    return [c.to_dict() for c in catalogs]


def list_schemas(client: Client, catalog: str) -> list[dict[str, Any]]:
    """Return all schemas inside a catalog.

    Args:
        client: Configured catalog client.
        catalog: Name of the parent catalog.

    Returns:
        A list of schema dicts.
    """
    response = _list_schemas.sync(client=client, catalog_name=catalog)
    if not isinstance(response, ListSchemasResponse):
        return []
    schemas = response.schemas
    if not isinstance(schemas, list):
        return []
    return [s.to_dict() for s in schemas]


def list_tables(client: Client, catalog: str, schema: str) -> list[dict[str, Any]]:
    """Return all tables inside a schema.

    Args:
        client: Configured catalog client.
        catalog: Name of the parent catalog.
        schema: Name of the parent schema.

    Returns:
        A list of table identifier dicts.
    """
    response = _list_tables.sync(
        client=client,
        catalog_name=catalog,
        schema_name=schema,
    )
    if not isinstance(response, ListTablesResponse):
        return []
    tables = response.tables
    if not isinstance(tables, list):
        return []
    return [t.to_dict() for t in tables]
