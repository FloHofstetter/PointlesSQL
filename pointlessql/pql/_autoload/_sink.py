# pyright: reportUnusedFunction=false
# These are package-internal helpers for the autoload orchestrator in
# this package's __init__; they are 'unused' only within this sub-module.
"""Target resolution, Delta append, and UC registration.

Internal helpers for :func:`pointlessql.pql.autoload`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass

import deltalake
import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogUnavailableError,
)
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._storage_options import storage_options_for
from pointlessql.pql._types import (
    ArrowTable,
)
from pointlessql.pql._write import derive_storage_location
from pointlessql.pql.engine import Engine

logger = logging.getLogger(__name__)


def _resolve_target_or_derive(
    client: Client,
    catalog: str,
    schema: str,
    table: str,
    full_name: str,
    unreachable_msg: str,
) -> tuple[str, bool]:
    """Resolve the target's storage location, deriving one when missing.

    Propagates :class:`CatalogNotFoundError` from
    :func:`derive_storage_location` when the table doesn't exist and
    the parent schema has no ``storage_root`` to derive one from.

    Args:
        client: Configured catalog client.
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.
        full_name: Three-part name (used for error messages).
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        ``(storage_location, target_exists)`` tuple.

    Raises:
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        UnexpectedStatus: For any non-404 soyuz-catalog error.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise
        response = None

    if isinstance(response, TableInfo):
        location = response.storage_location
        if not isinstance(location, Unset) and location:
            return (location, True)

    derived = derive_storage_location(client, catalog, schema, table)
    return (derived, False)


def _append_to_delta(target_location: str, arrow_table: ArrowTable) -> None:
    """Append *arrow_table* to the Delta table at *target_location*.

    Uses ``deltalake.write_deltalake(mode="append")`` which creates
    the table on the first call.  No schema-evolution flags — the
    MVP requires the second-and-subsequent files to match the
    bootstrap schema.  Schema-drift handling is deferred.

    Args:
        target_location: Delta table storage URI.
        arrow_table: Augmented data to append.
    """
    # ``ArrowTable`` Protocol matches the pyarrow.Table runtime shape;
    # deltalake's stub typing wants its own ArrowArrayExportable union,
    # so we drop to Any at the boundary.
    deltalake.write_deltalake(
        target_location,
        cast(Any, arrow_table),
        mode="append",
        storage_options=storage_options_for(target_location),
    )


def _register_target_in_uc(
    *,
    client: Client,
    engine: Engine,
    catalog: str,
    schema: str,
    table: str,
    location: str,
    arrow_for_columns: ArrowTable,
    unreachable_msg: str,
) -> None:
    """Register a freshly-created Delta table in soyuz-catalog.

    Mirrors the catalog-side bookkeeping
    :func:`pointlessql.pql._write.write_table` does after a
    create-mode write so an autoload-bootstrapped table is
    indistinguishable from one written through the editor.

    The columns metadata is derived by handing the augmented
    Arrow table to :class:`pointlessql.pql.engine.Engine` —
    converting Arrow → engine frame is unnecessary because the
    engine's :meth:`columns_info` accepts any frame whose schema
    can be read by inspection (pandas via ``pa.Table.to_pandas``
    on the column metadata).

    Args:
        client: Configured catalog client.
        engine: PQL engine (used for column metadata).
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.
        location: Storage URI of the new Delta table.
        arrow_for_columns: Arrow table whose schema describes the
            columns to register.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Raises:
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    pandas_for_meta = arrow_for_columns.to_pandas()
    columns = columns_from_tuples(engine.columns_info(pandas_for_meta))
    body = CreateTable(
        catalog_name=catalog,
        schema_name=schema,
        name=table,
        table_type="MANAGED",
        data_source_format="DELTA",
        columns=columns,
        storage_location=location,
    )
    try:
        _create_table.sync(client=client, body=body)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
