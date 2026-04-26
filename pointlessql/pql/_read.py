"""Module-level helper for :meth:`PQL.table`."""

from __future__ import annotations

from typing import Any

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine


def read_table(
    *,
    client: Client,
    engine: Engine,
    full_name: str,
    unreachable_msg: str,
) -> Any:
    """Read a Delta table registered in Unity Catalog.

    Args:
        client: A configured ``soyuz_catalog_client.Client`` instance.
        engine: The engine to materialise the Delta scan with.
        full_name: Three-part name ``"catalog.schema.table"``.
        unreachable_msg: Pre-rendered "cannot reach catalog" message
            so the caller controls how the URL appears (it lives on
            ``client._base_url`` which is private).

    Returns:
        The table contents in the engine's native frame type
        (e.g. pandas DataFrame, DuckDB relation).

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the table is not found or has no
            ``storage_location``.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    parse_full_name(full_name)  # validates format
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        msg = f"Table not found: {full_name!r}"
        raise CatalogNotFoundError(msg)

    location = response.storage_location
    if isinstance(location, Unset) or not location:
        msg = f"Table {full_name!r} has no storage_location"
        raise CatalogNotFoundError(msg)

    return engine.read(location)
