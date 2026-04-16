"""Sync bridge between Unity Catalog metadata and Delta Lake DataFrames."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.api.catalogs import (
    list_catalogs_api_2_1_unity_catalog_catalogs_get as _list_catalogs,
)
from soyuz_catalog_client.api.schemas import (
    get_schema_api_2_1_unity_catalog_schemas_full_name_get as _get_schema,
)
from soyuz_catalog_client.api.schemas import (
    list_schemas_api_2_1_unity_catalog_schemas_get as _list_schemas,
)
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.api.tables import (
    list_tables_api_2_1_unity_catalog_tables_get as _list_tables,
)
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.list_tables_response import ListTablesResponse
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import CatalogNotFoundError, CatalogUnavailableError
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine, make_engine
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.settings import Settings


class PQL:
    """Sync bridge between Unity Catalog metadata and Delta Lake DataFrames.

    Designed for interactive use in notebooks and scripts.  All methods
    are synchronous — the web UI's async wrapper
    (``pointlessql.services.unitycatalog``) is a separate concern.

    Args:
        client: An existing ``soyuz_catalog_client.Client`` instance.
            When ``None``, one is built via ``make_soyuz_client()``.
        settings: Optional ``Settings`` override.  Used for both
            client creation and engine selection when not provided
            explicitly.
        engine: Engine instance, engine name string, or ``None``.
            When ``None``, auto-selects from ``settings.engine``
            (default ``"pandas"``).
    """

    def __init__(
        self,
        client: Client | None = None,
        settings: Settings | None = None,
        engine: Engine | str | None = None,
    ) -> None:
        resolved = settings or Settings()
        self._client = client or make_soyuz_client(resolved)
        if engine is None:
            self._engine = make_engine(resolved.engine)
        elif isinstance(engine, str):
            self._engine = make_engine(engine)
        else:
            self._engine = engine

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def table(self, full_name: str) -> Any:
        """Read a Delta table registered in Unity Catalog.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.

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
            response = _get_table.sync(client=self._client, full_name=full_name)
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(self._unreachable_msg()) from exc
        if not isinstance(response, TableInfo):
            msg = f"Table not found: {full_name!r}"
            raise CatalogNotFoundError(msg)

        location = response.storage_location
        if isinstance(location, Unset) or not location:
            msg = f"Table {full_name!r} has no storage_location"
            raise CatalogNotFoundError(msg)

        return self._engine.read(location)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_table(
        self,
        df: Any,
        full_name: str,
        *,
        mode: Literal["error", "append", "overwrite", "ignore"] = "overwrite",
    ) -> None:
        """Write a frame to a Delta table and register it in the catalog.

        If the table already exists in the catalog its data is replaced
        (or appended to, depending on *mode*).  If the table does not
        exist yet it is created with column metadata derived from *df*.

        Args:
            df: The data to write, in the engine's native frame type.
            full_name: Three-part name ``"catalog.schema.table"``.
            mode: Write mode passed to the engine.  Defaults to
                ``"overwrite"``.

        Raises:
            ValidationError: If *full_name* does not have exactly three parts.
            CatalogNotFoundError: If the parent schema has no storage root
                and the table does not already exist.
            CatalogUnavailableError: If soyuz-catalog is unreachable.
        """  # noqa: DOC503
        catalog, schema, table = parse_full_name(full_name)

        # Determine storage_location and whether the table already exists.
        table_exists = False
        location: str | None = None

        try:
            response = _get_table.sync(client=self._client, full_name=full_name)
            if isinstance(response, TableInfo):
                loc = response.storage_location
                if not isinstance(loc, Unset) and loc:
                    location = loc
                    table_exists = True
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(self._unreachable_msg()) from exc
        except UnexpectedStatus as exc:
            if exc.status_code != 404:
                raise

        try:
            if not table_exists:
                location = self._derive_storage_location(catalog, schema, table)

            assert location is not None  # noqa: S101 — guarded above

            self._engine.write(df, location, mode)

            if not table_exists:
                columns = columns_from_tuples(self._engine.columns_info(df))
                body = CreateTable(
                    catalog_name=catalog,
                    schema_name=schema,
                    name=table,
                    table_type="MANAGED",
                    data_source_format="DELTA",
                    columns=columns,
                    storage_location=location,
                )
                _create_table.sync(client=self._client, body=body)
        except httpx.ConnectError as exc:
            raise CatalogUnavailableError(self._unreachable_msg()) from exc

    # ------------------------------------------------------------------
    # Convenience list methods
    # ------------------------------------------------------------------

    def list_catalogs(self) -> list[dict[str, Any]]:
        """Return all catalogs visible to the caller.

        Returns:
            A list of catalog dicts with at least a ``"name"`` key.
        """
        response = _list_catalogs.sync(client=self._client)
        if not isinstance(response, ListCatalogsResponse):
            return []
        catalogs = response.catalogs
        if not isinstance(catalogs, list):
            return []
        return [c.to_dict() for c in catalogs]

    def list_schemas(self, catalog: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Args:
            catalog: Name of the parent catalog.

        Returns:
            A list of schema dicts.
        """
        response = _list_schemas.sync(client=self._client, catalog_name=catalog)
        if not isinstance(response, ListSchemasResponse):
            return []
        schemas = response.schemas
        if not isinstance(schemas, list):
            return []
        return [s.to_dict() for s in schemas]

    def list_tables(self, catalog: str, schema: str) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Args:
            catalog: Name of the parent catalog.
            schema: Name of the parent schema.

        Returns:
            A list of table identifier dicts.
        """
        response = _list_tables.sync(
            client=self._client,
            catalog_name=catalog,
            schema_name=schema,
        )
        if not isinstance(response, ListTablesResponse):
            return []
        identifiers = response.identifiers
        if not isinstance(identifiers, list):
            return []
        return [t.to_dict() for t in identifiers]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unreachable_msg(self) -> str:
        """Build a user-friendly message when soyuz-catalog is unreachable."""
        url = self._client._base_url  # pyright: ignore[reportPrivateUsage]
        return f"Cannot reach soyuz-catalog at {url}. Is the server running?"

    def _derive_storage_location(
        self, catalog: str, schema: str, table: str
    ) -> str:
        """Compute a storage location for a new table from its parent schema.

        Args:
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
        response = _get_schema.sync(client=self._client, full_name=schema_full)
        if not isinstance(response, SchemaInfo):
            msg = f"Schema not found: {schema_full!r}"
            raise CatalogNotFoundError(msg)

        # Prefer storage_location, fall back to storage_root.
        for field in (response.storage_location, response.storage_root):
            if not isinstance(field, Unset) and field:
                return f"{field.rstrip('/')}/{table}"

        msg = (
            f"Schema {schema_full!r} has no storage_location or storage_root. "
            f"Set a storage_root on the schema before writing new tables."
        )
        raise CatalogNotFoundError(msg)
