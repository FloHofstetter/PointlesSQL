"""Helpers for :meth:`PQL.write_table` (Sprint-78 split)."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
)
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine


def write_table(
    *,
    client: Client,
    engine: Engine,
    df: Any,
    full_name: str,
    mode: Literal["error", "append", "overwrite", "ignore"],
    unreachable_msg: str,
) -> None:
    """Write a frame to a Delta table and register it in the catalog.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: Engine to write *df* with.
        df: The data to write, in the engine's native frame type.
        full_name: Three-part name ``"catalog.schema.table"``.
        mode: Write mode passed to the engine.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Raises:
        ValidationError: If *full_name* does not have exactly three parts.
        CatalogNotFoundError: If the parent schema has no storage root
            and the table does not already exist.
        CatalogUnavailableError: If soyuz-catalog is unreachable.
    """  # noqa: DOC503
    catalog, schema, table = parse_full_name(full_name)

    table_exists = False
    location: str | None = None

    try:
        response = _get_table.sync(client=client, full_name=full_name)
        if isinstance(response, TableInfo):
            loc = response.storage_location
            if not isinstance(loc, Unset) and loc:
                location = loc
                table_exists = True
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise

    try:
        if not table_exists:
            location = derive_storage_location(client, catalog, schema, table)

        assert location is not None  # noqa: S101 — guarded above

        engine.write(df, location, mode)

        if not table_exists:
            columns = columns_from_tuples(engine.columns_info(df))
            body = CreateTable(
                catalog_name=catalog,
                schema_name=schema,
                name=table,
                table_type="MANAGED",
                data_source_format="DELTA",
                columns=columns,
                storage_location=location,
            )
            _create_table.sync(client=client, body=body)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc


def derive_storage_location(
    client: Client, catalog: str, schema: str, table: str
) -> str:
    """Compute a storage location for a new table from its parent schema.

    Args:
        client: Configured catalog client.
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.

    Returns:
        The derived storage location path.

    Raises:
        CatalogNotFoundError: If the parent schema has no
            ``storage_location`` or ``storage_root``.
    """
    schema_full = f"{catalog}.{schema}"
    response = _get_schema.sync(client=client, full_name=schema_full)
    if not isinstance(response, SchemaInfo):
        msg = f"Schema not found: {schema_full!r}"
        raise CatalogNotFoundError(msg)

    for field in (response.storage_location, response.storage_root):
        if not isinstance(field, Unset) and field:
            return f"{field.rstrip('/')}/{table}"

    msg = (
        f"Schema {schema_full!r} has no storage_location or storage_root. "
        f"Set a storage_root on the schema before writing new tables."
    )
    raise CatalogNotFoundError(msg)
