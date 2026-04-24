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

from pointlessql.pql._autoload import AutoloadFormat, autoload_files
from pointlessql.pql._list import list_catalogs, list_schemas, list_tables
from pointlessql.pql._merge import MergeStrategy, merge_table
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

    Sprint 13.6 added an explicit ``principal`` argument so a Hermes
    plugin (or any other process spawning PQL programmatically) can
    pass the agent's principal without mutating the process env.
    Resolution order: explicit ``client`` wins; otherwise an explicit
    ``principal`` argument; otherwise the ``POINTLESSQL_PRINCIPAL``
    env var; otherwise an unforwarded client.

    Args:
        client: An existing ``soyuz_catalog_client.Client`` instance.
            When ``None``, one is built via ``make_soyuz_client()`` (or
            ``make_principal_client()`` if a principal is found).
        settings: Optional ``Settings`` override.  Used for both
            client creation and engine selection when not provided
            explicitly.
        engine: Engine instance, engine name string, or ``None``.
            When ``None``, auto-selects from ``settings.delta.engine``
            (default ``"pandas"``).
        principal: Explicit X-Principal value forwarded on every UC
            call.  Wins over ``POINTLESSQL_PRINCIPAL``.  ``None``
            falls back to the env var.
    """

    def __init__(
        self,
        client: Client | None = None,
        settings: Settings | None = None,
        engine: Engine | str | None = None,
        *,
        principal: str | None = None,
    ) -> None:
        resolved = settings or Settings()
        if client is not None:
            self._client = client
        else:
            effective = principal or os.environ.get("POINTLESSQL_PRINCIPAL")
            if effective:
                self._client = make_principal_client(resolved, effective)
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

    def merge(
        self,
        source: Any,
        target: str,
        *,
        on: list[str],
        strategy: MergeStrategy = "upsert",
    ) -> dict[str, Any]:
        """Merge *source* into the existing Delta table at *target*.

        Sprint 13.5.2.  Two strategies:

        * ``"upsert"`` — match on *on* keys, update all non-key
          columns from source on match, insert new rows otherwise.
        * ``"scd2"`` — append-only history: source rows gain
          ``_valid_from`` / ``_valid_to`` / ``_is_current`` columns;
          a key match closes the current target row and appends the
          new version.  See
          :mod:`pointlessql.pql._merge` for the no-change-detection
          caveat (the MVP closes + reopens for every key match).

        Args:
            source: A pandas DataFrame, PyArrow Table, or UC
                ``"catalog.schema.table"`` reference (resolved
                through :meth:`table` when a string).
            target: UC ``"catalog.schema.table"`` reference.  Must
                already exist — use :meth:`write_table` (or, when
                Sprint 13.5.3 lands, :meth:`autoload`) to bootstrap.
            on: Non-empty list of merge-key column names.
            strategy: ``"upsert"`` (default) or ``"scd2"``.

        Returns:
            A dict carrying ``strategy`` and the deltalake merge
            stats.  SCD-2 also reports ``rows_appended`` and the
            close-phase stats.
        """
        return merge_table(
            client=self._client,
            engine=self._engine,
            source=source,
            target=target,
            on=on,
            strategy=strategy,
            unreachable_msg=self._unreachable_msg(),
        )

    def autoload(
        self,
        source_path: str,
        target: str,
        *,
        source_system: str = "",
        file_format: AutoloadFormat = "auto",
    ) -> dict[str, Any]:
        """Lift files from a Volume directory into a bronze Delta table.

        Sprint 13.5.3.  DuckDB type-infers each file
        (``read_parquet`` / ``read_csv_auto`` / ``read_json_auto``),
        the audit columns from
        :func:`pointlessql.conventions.load_conventions` are
        injected on every row, and the result appends to the target
        Delta table.  File-level exactly-once: a SHA-256 of the file
        bytes is recorded in ``autoload_checkpoints`` after a
        successful append, so re-running the autoload over the same
        directory is a no-op for previously-ingested files.

        Args:
            source_path: Local filesystem directory (recursive walk)
                or glob pattern.  Volumes-as-managed-directories —
                HTTP-fetched-Volume support is a follow-up sprint.
            target: UC ``"catalog.schema.table"`` string.  When the
                target doesn't exist it is created on the first
                successful append, using the parent schema's
                ``storage_root``.
            source_system: Free-form upstream-system identifier
                written into the ``_source_system`` audit column.
                Empty default for dev / smoke; production callers
                should pass a real value.
            file_format: ``"auto"`` (per-file extension), or one of
                ``"parquet"`` / ``"csv"`` / ``"json"`` to force.

        Returns:
            ``{"target", "files_scanned", "files_ingested",
            "files_skipped", "rows_ingested"}``.
        """
        from pointlessql.db import get_session_factory

        return autoload_files(
            client=self._client,
            engine=self._engine,
            session_factory=get_session_factory(),
            source_path=source_path,
            target=target,
            source_system=source_system,
            file_format=file_format,
            conventions=None,
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
