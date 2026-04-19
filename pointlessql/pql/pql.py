"""Sync bridge between Unity Catalog metadata and Delta Lake DataFrames.

Sprint 78 — split into ``_types`` (SQLResult), ``_read``, ``_sql``,
``_write``, ``_list`` siblings. The :class:`PQL` class stays here as
the public façade; method bodies delegate to the sibling helpers so
the orchestration shape (init → method dispatch) is readable in one
file while the per-concern logic lives next door.

``SQLResult`` is re-exported from this module so existing
``from pointlessql.pql.pql import SQLResult`` callers (notably the
test suite) continue to resolve unchanged.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from soyuz_catalog_client import Client

from pointlessql.pql._list import list_catalogs, list_schemas, list_tables
from pointlessql.pql._read import read_table
from pointlessql.pql._sql import run_sql
from pointlessql.pql._types import SQLResult
from pointlessql.pql._write import write_table
from pointlessql.pql.engine import Engine, make_engine
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
from pointlessql.settings import Settings

__all__ = ["PQL", "SQLResult"]


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

    def table(self, full_name: str) -> Any:
        """Read a Delta table registered in Unity Catalog.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.

        Returns:
            The table contents in the engine's native frame type
            (e.g. pandas DataFrame, DuckDB relation).
        """
        return read_table(
            client=self._client,
            engine=self._engine,
            full_name=full_name,
            unreachable_msg=self._unreachable_msg(),
        )

    @staticmethod
    def sql(
        query: str,
        *,
        approved_tables: dict[str, str],
        max_rows: int = 10_000,
        conn: Any = None,
        explain: bool = False,
    ) -> SQLResult:
        """Run a single SELECT against DuckDB with UC-backed views.

        Thin façade over :func:`pointlessql.pql._sql.run_sql` — the
        helper handles parsing, the approved-tables guard, view
        registration, execution, row-cap slicing, and result framing.

        Args:
            query: The user-entered SQL.  Must be a single SELECT.
            approved_tables: Mapping of fully-qualified table name to
                its Delta storage location.
            max_rows: Post-execution row cap.
            conn: Optional pre-created DuckDB connection.
            explain: When ``True``, return the EXPLAIN ANALYZE output.

        Returns:
            A :class:`SQLResult` with columns, rows, and metrics.
        """
        return run_sql(
            query,
            approved_tables=approved_tables,
            max_rows=max_rows,
            conn=conn,
            explain=explain,
        )

    def write_table(
        self,
        df: Any,
        full_name: str,
        *,
        mode: Literal["error", "append", "overwrite", "ignore"] = "overwrite",
    ) -> None:
        """Write a frame to a Delta table and register it in the catalog.

        Args:
            df: The data to write.
            full_name: Three-part name ``"catalog.schema.table"``.
            mode: Write mode passed to the engine.  Defaults to
                ``"overwrite"``.
        """
        write_table(
            client=self._client,
            engine=self._engine,
            df=df,
            full_name=full_name,
            mode=mode,
            unreachable_msg=self._unreachable_msg(),
        )

    def list_catalogs(self) -> list[dict[str, Any]]:
        """Return all catalogs visible to the caller.

        Returns:
            A list of catalog dicts with at least a ``"name"`` key.
        """
        return list_catalogs(self._client)

    def list_schemas(self, catalog: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Args:
            catalog: Name of the parent catalog.

        Returns:
            A list of schema dicts.
        """
        return list_schemas(self._client, catalog)

    def list_tables(self, catalog: str, schema: str) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Args:
            catalog: Name of the parent catalog.
            schema: Name of the parent schema.

        Returns:
            A list of table identifier dicts.
        """
        return list_tables(self._client, catalog, schema)

    def _unreachable_msg(self) -> str:
        """Build a user-friendly message when soyuz-catalog is unreachable."""
        url = self._client._base_url  # pyright: ignore[reportPrivateUsage]
        return f"Cannot reach soyuz-catalog at {url}. Is the server running?"
