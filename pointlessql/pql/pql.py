"""Sync bridge between Unity Catalog metadata and Delta Lake DataFrames."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from soyuz_catalog_client import Client
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
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.list_tables_response import ListTablesResponse
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql.engine import Engine, make_engine, register_delta_view
from pointlessql.pql.sql_parser import SQLParseError, prepare_sql
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
from pointlessql.settings import Settings


@dataclass(frozen=True)
class SQLResult:
    """The outcome of a Phase-12 :meth:`PQL.sql` execution.

    All fields are JSON-encodable so the route handler can serialise
    the result straight into a ``JSONResponse`` body.

    Attributes:
        columns: One dict per output column with ``name`` and
            stringified DuckDB ``type``.
        rows: The result rows as a list of lists (column order matches
            :attr:`columns`).
        row_count: Length of :attr:`rows` after any row-cap slicing.
        truncated: ``True`` iff the underlying query produced more
            rows than ``max_rows`` and the excess was dropped.
        duration_ms: Wall-clock execution time on the DuckDB engine.
        executed_sql: The SQL string the caller supplied (unchanged).
        rewritten_sql: What was actually sent to DuckDB after the
            3-part → single-quoted-identifier rewrite.
        referenced_tables: The list of UC ``catalog.schema.table``
            references extracted from the parsed SQL.
    """

    columns: list[dict[str, str]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    executed_sql: str
    rewritten_sql: str
    referenced_tables: list[str]


class PQL:
    """Sync bridge between Unity Catalog metadata and Delta Lake DataFrames.

    Designed for interactive use in notebooks and scripts.  All methods
    are synchronous — the web UI's async wrapper
    (``pointlessql.services.unitycatalog``) is a separate concern.

    When the ``POINTLESSQL_PRINCIPAL`` environment variable is set and no
    explicit ``client`` is passed, the constructor builds a
    principal-forwarded client via ``make_principal_client()`` so every
    catalog call carries an ``X-Principal`` header. The Sprint 24
    Papermill executor uses this to make notebook code that instantiates
    ``PQL()`` inherit the job's run-as user without any extra wiring —
    regular interactive use is unaffected.

    Args:
        client: An existing ``soyuz_catalog_client.Client`` instance.
            When ``None``, one is built via ``make_soyuz_client()`` (or
            ``make_principal_client()`` if ``POINTLESSQL_PRINCIPAL`` is
            set).
        settings: Optional ``Settings`` override.  Used for both
            client creation and engine selection when not provided
            explicitly.
        engine: Engine instance, engine name string, or ``None``.
            When ``None``, auto-selects from ``settings.delta.engine``
            (default ``"pandas"``).
    """

    def __init__(
        self,
        client: Client | None = None,
        settings: Settings | None = None,
        engine: Engine | str | None = None,
    ) -> None:
        resolved = settings or Settings()
        if client is not None:
            self._client = client
        else:
            principal = os.environ.get("POINTLESSQL_PRINCIPAL")
            if principal:
                self._client = make_principal_client(resolved, principal)
            else:
                self._client = make_soyuz_client(resolved)
        if engine is None:
            self._engine = make_engine(resolved.delta.engine)
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
    # SQL execution (Phase 12)
    # ------------------------------------------------------------------

    @staticmethod
    def sql(
        query: str,
        *,
        approved_tables: dict[str, str],
        max_rows: int = 10_000,
        conn: Any = None,
    ) -> SQLResult:
        """Run a single SELECT against DuckDB with UC-backed views.

        The caller is responsible for enforcement: every 3-part
        reference parsed out of *query* must appear in
        *approved_tables* mapped to its Delta ``storage_location``.
        The method will refuse to execute if a reference is missing
        so a silent privilege-check bypass cannot leak data.

        The optional *conn* argument lets the route layer pre-create
        the :class:`duckdb.DuckDBPyConnection` so it can register
        the handle in its cancel registry before the thread starts
        running.  When omitted the method opens and closes its own
        connection — that is the notebook-style entry point that
        Phase 12 keeps for callers that do not need cancel.

        Args:
            query: The user-entered SQL.  Must be a single SELECT.
            approved_tables: Mapping of fully-qualified table name to
                its Delta storage location.  Keys must be a superset
                of the table references extracted from *query*.
            max_rows: Post-execution row cap.  Extra rows are dropped
                and :attr:`SQLResult.truncated` is set to ``True``.
                Set by ``POINTLESSQL_SQL_MAX_ROWS`` in normal use.
            conn: Optional pre-created DuckDB connection.  When
                provided, the method uses it and leaves it open —
                the caller owns the lifecycle.  When ``None`` a
                fresh connection is created and closed here.

        Returns:
            A :class:`SQLResult` with columns, rows, and metrics.

        Raises:
            SQLExecutionError: If *query* fails to parse, falls
                outside Phase-12's SELECT-only scope, or DuckDB
                rejects it at execution time.
            ValidationError: If a referenced table is not present in
                *approved_tables* (defence-in-depth against a route
                that forgot to enforce).
        """
        import duckdb

        try:
            prepared = prepare_sql(query)
        except SQLParseError as exc:
            raise SQLExecutionError(str(exc)) from exc
        missing = [r for r in prepared.refs if r not in approved_tables]
        if missing:
            msg = (
                f"Cannot execute: table reference(s) {missing!r} were not "
                f"approved by the route layer. This is a bug in the caller."
            )
            raise ValidationError(msg)

        owns_conn = conn is None
        if owns_conn:
            conn = duckdb.connect()
        try:
            for ref in prepared.refs:
                register_delta_view(conn, ref, approved_tables[ref])

            start = time.perf_counter()
            try:
                arrow_result = conn.execute(prepared.rewritten_sql).to_arrow_table()
            except duckdb.Error as exc:
                raise SQLExecutionError(str(exc)) from exc
            duration_ms = int((time.perf_counter() - start) * 1000)

            total = arrow_result.num_rows
            if total > max_rows:
                arrow_result = arrow_result.slice(0, max_rows)
                truncated = True
            else:
                truncated = False

            columns = [
                {"name": name, "type": str(arrow_result.schema.field(name).type)}
                for name in arrow_result.column_names
            ]
            # Convert to JSON-friendly lists.  ``to_pylist`` yields a
            # list of dicts keyed by column name; flatten to lists so
            # the frontend's listTable can iterate positionally.
            rows_as_dicts = arrow_result.to_pylist()
            col_names = list(arrow_result.column_names)
            rows = [[row.get(c) for c in col_names] for row in rows_as_dicts]

            return SQLResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                duration_ms=duration_ms,
                executed_sql=query,
                rewritten_sql=prepared.rewritten_sql,
                referenced_tables=list(prepared.refs),
            )
        finally:
            if owns_conn:
                conn.close()

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
        tables = response.tables
        if not isinstance(tables, list):
            return []
        return [t.to_dict() for t in tables]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unreachable_msg(self) -> str:
        """Build a user-friendly message when soyuz-catalog is unreachable."""
        url = self._client._base_url  # pyright: ignore[reportPrivateUsage]
        return f"Cannot reach soyuz-catalog at {url}. Is the server running?"

    def _derive_storage_location(self, catalog: str, schema: str, table: str) -> str:
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
