# pyright: reportUnusedClass=false
"""Data-ops mixin for the :class:`PQL` façade — read / write / merge / sql / vector / list."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pointlessql.pql._aggregate import AggregateMode, AggSpec, aggregate_table
from pointlessql.pql._autoload import AutoloadFormat, autoload_files
from pointlessql.pql._list import list_catalogs, list_schemas, list_tables
from pointlessql.pql._merge import MergeStrategy, merge_table
from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._read import read_table
from pointlessql.pql._sql import run_sql
from pointlessql.pql._types import SQLResult
from pointlessql.pql._update_delete import delete_table_rows, update_table
from pointlessql.pql._write import write_table


class _DataOpsMixin(_PQLBase):
    """Read, write, merge, SQL, vector, list, update, delete, aggregate, autoload, widgets."""

    def table(self, full_name: str) -> Any:
        """Read a Delta table registered in Unity Catalog.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
                When the kernel's :mod:`pointlessql.pql.context` carries
                an active branch binding (Phase 102 Wave-D), the
                schema segment is rewritten on the fly so the read
                follows the binding without the caller spelling it
                out.  Reads falling through to a table the branch
                does not carry surface ``BranchNotFoundError`` and
                callers can fall back to the canonical FQN with
                ``with_branch=False``-style overrides in a future
                follow-up.

        Returns:
            The table contents in the engine's native frame type
            (e.g. pandas DataFrame, DuckDB relation).
        """
        return read_table(
            client=self._client,
            engine=self._engine,
            full_name=self._branch_remap(full_name),
            unreachable_msg=self._unreachable_msg(),
        )

    def table_at_version(self, full_name: str, version: int) -> Any:
        """Read a Delta table as of a specific historical version.

        Always materialises through pandas — the engine abstraction
        targets current-version reads only, and per-engine
        ``load_as_version`` would surface near-identical code.
        Records a ``query_history`` row with
        ``read_kind="pql_table_at_version"`` so the time-travel read
        shows up in ``/queries``.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
            version: Target Delta version.  ``0`` is the initial
                commit; subsequent commits monotonically increment.

        Returns:
            A pandas DataFrame as the table looked at *version*.
        """
        from pointlessql.pql._time_travel import read_table_at_version

        return read_table_at_version(
            client=self._client,
            full_name=full_name,
            version=version,
            unreachable_msg=self._unreachable_msg(),
        )

    def table_at_timestamp(self, full_name: str, when: Any) -> Any:
        """Read a Delta table as it looked at wall-clock instant *when*.

        Resolves to a Delta version via
        :meth:`deltalake.DeltaTable.load_as_version` (the public API
        accepts a datetime).

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
            when: Timezone-aware ``datetime``.

        Returns:
            A pandas DataFrame as the table looked at *when*.
        """
        from pointlessql.pql._time_travel import read_table_at_timestamp

        return read_table_at_timestamp(
            client=self._client,
            full_name=full_name,
            when=when,
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

        Lineage propagation: when a referenced source
        table carries ``_lineage_row_id`` and the agent will feed the
        result frame into :meth:`write_table` or :meth:`merge` with
        row-edges expected, the SELECT must explicitly project the
        column (``SELECT t._lineage_row_id AS _lineage_row_id, …``).
        Without it, the downstream audit hook short-circuits — no
        source IDs to correlate on, so ``lineage_row_edges`` records
        nothing and every further table inherits the gap.  An INFO
        log + ``lineage_row_id_dropped_at_select`` flag on the op's
        ``params_json`` surfaces the omission for run-detail review.

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
        source_table_fqn: str | None = None,
        source_model_uri: str | None = None,
        derivations: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """Write a frame to a Delta table and register it in the catalog.

        Args:
            df: The data to write.
            full_name: Three-part name ``"catalog.schema.table"``.
            mode: Write mode passed to the engine.  Defaults to
                ``"overwrite"``.
            source_table_fqn: Optional UC FQN of the upstream table
                that produced *df*.  When set, drives the OpenLineage
                event so the resulting edge ``source_table_fqn →
                full_name`` shows up on the lineage card.
            source_model_uri: optional registered-model
                URI ``models:/cat.sch.model/<version>`` declaring
                that *df* is the output of inference against a model.
                Stamps every row-edge with the model URI so the
                model-detail Lineage DAG can paint *full_name* as a
                downstream prediction node.  Requires
                ``source_table_fqn`` AND ``_lineage_row_id`` on *df*
                ( caveat) — without either, the row-edge
                hook short-circuits and the URI has nowhere to land.
            derivations: Optional declarative mapping of derived
                target columns to their *true* source-column names.
                Effective only when ``source_table_fqn`` is also set.
        """
        write_table(
            client=self._client,
            engine=self._engine,
            df=df,
            full_name=self._branch_remap(full_name),
            mode=mode,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
            source_table_fqn=source_table_fqn,
            source_model_uri=source_model_uri,
            derivations=derivations,
        )

    def merge(
        self,
        source: Any,
        target: str,
        *,
        on: list[str],
        strategy: MergeStrategy = "upsert",
        source_table_fqn: str | None = None,
        source_model_uri: str | None = None,
        track_rejects: bool = False,
        track_value_changes: bool = False,
        derivations: Mapping[str, Sequence[str]] | None = None,
    ) -> dict[str, Any]:
        """Merge *source* into the existing Delta table at *target*.

        Two strategies:

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
                already exist — use :meth:`write_table` or
                :meth:`autoload` to bootstrap.
            on: Non-empty list of merge-key column names.
            strategy: ``"upsert"`` (default) or ``"scd2"``.
            source_table_fqn: Optional UC FQN of the upstream table
                that produced *source*.  When set, drives the
                OpenLineage event so the resulting edge
                ``source_table_fqn → target`` shows up on the lineage
                card.  When *source* is itself a UC string the helper
                derives this automatically below.
            source_model_uri: optional registered-model
                URI ``models:/cat.sch.model/<version>`` declaring
                that *source* is the output of inference against a
                model.  Stamps every row-edge with the model URI so
                the model-detail Lineage DAG can paint *target* as a
                downstream prediction node when merging into a
                pre-existing predictions table.
            track_rejects: When ``True``, scan the source pre-merge
                for rows that won't land (NULL ``on`` key, duplicate
                key in source) and record them on
                ``lineage_row_rejects`` so the run-detail UI can
                explain dropped rows.  Default
                ``False`` keeps the cost off the hot path.
            track_value_changes: First merge after a fresh
                :meth:`write_table` produces only ``insert`` CDF
                events, which the helper deliberately skips —
                value-change rows start landing on the second merge
                where ``update_preimage`` / ``update_postimage``
                pairs are emitted ( doc-pin).  When ``True`` and
                ``strategy="upsert"``, read the Delta Change Data
                Feed for the merge's commit range and record one
                ``lineage_value_changes`` row per actually-different
                cell on a matched-and-updated target row (Sprint
                15.7.3).  Silently ignored on ``strategy="scd2"``.
                Default ``False`` keeps the CDF read off the hot
                path.
            derivations: Optional declarative mapping of derived
                target columns to their *true* source-column names.
                Lets the column-trace UI surface upstream-of-merge
                ``.assign(...)`` derivations.

        Returns:
            A dict carrying ``strategy`` and the deltalake merge
            stats.  SCD-2 also reports ``rows_appended`` and the
            close-phase stats.
        """
        derived_source_fqn = source_table_fqn or (source if isinstance(source, str) else None)
        return merge_table(
            client=self._client,
            engine=self._engine,
            source=source,
            target=target,
            on=on,
            strategy=strategy,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
            source_table_fqn=derived_source_fqn,
            source_model_uri=source_model_uri,
            track_rejects=track_rejects,
            track_value_changes=track_value_changes,
            derivations=derivations,
        )

    def vector_index(
        self,
        table: str,
        column: str,
        *,
        dim: int | None = None,
        model: str = "all-MiniLM-L6-v2",
        embedder: str | Any = "sentence_transformers",
        metric: Literal["cosine", "l2", "ip"] = "cosine",
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 128,
        rebuild: bool = False,
        workspace_id: int | None = None,
    ) -> dict[str, Any]:
        """Create or rebuild an HNSW vector index over ``table.column``.

        Backed by the DuckDB ``vss`` extension; the index file lives
        at ``<table.storage_location>/_vss/<column>.duckdb`` so a
        table-drop sweeps the index and a workspace export captures
        it.  After the first build, :meth:`merge` writes auto-rebuild
        the index incrementally via the post-commit hook.

        Args:
            table: Three-part UC ``"catalog.schema.table"`` reference.
            column: Source text column on *table*.
            dim: Output vector dimensionality.  ``None`` lets the
                embedder pick its built-in default.
            model: Provider-specific model identifier (e.g.
                ``"all-MiniLM-L6-v2"`` for the default
                ``sentence_transformers`` provider).
            embedder: Either a registry key
                (``"sentence_transformers"``, ``"openai"``,
                ``"hermes"``) or a pre-constructed embedder instance
                (test injection).
            metric: Similarity metric.  ``"cosine"`` is the default
                and the only metric exercised by the chat-panel
                retrieval flow.
            hnsw_m: HNSW ``m`` (max neighbours) build parameter;
                duckdb-vss default 16 is sane for ≤1M rows.
            hnsw_ef_construction: HNSW build-time candidate list
                size; duckdb-vss default 128 is sane for ≤1M rows.
            rebuild: When ``True``, drop and rebuild the index file
                from scratch even when no Delta version change is
                detected.
            workspace_id: PointlesSQL workspace owning the index.
                ``None`` skips the metadata-DB row (interactive
                REPL); the REST path sets this from the request
                context.

        Returns:
            Dict with ``index_id`` (autoincrement int or ``None`` in
            REPL mode), ``path``, ``dim``, ``rows_indexed``,
            ``delta_version_indexed``, ``built_at``, etc.
        """
        from typing import cast

        from pointlessql.pql._vector import create_or_rebuild_index
        from pointlessql.types import RunId

        return create_or_rebuild_index(
            client=self._client,
            table=table,
            column=column,
            dim=dim,
            model=model,
            embedder=embedder,
            metric=metric,
            hnsw_m=hnsw_m,
            hnsw_ef_construction=hnsw_ef_construction,
            rebuild=rebuild,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=cast(RunId | None, self._current_run_id),
            workspace_id=workspace_id,
        )

    def vector_search(
        self,
        table: str,
        column: str,
        query: str,
        *,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run a top-K semantic search against an existing vector index.

        Args:
            table: Three-part UC ``"catalog.schema.table"`` reference.
            column: Source column on *table* — must already have an
                index built via :meth:`vector_index`.
            query: Free-text query string.  Embedded with the same
                provider that built the index.
            top_k: Number of hits to return (1–200).

        Returns:
            Dict with ``hits`` (list of ``{score, pk, snippet}``)
            plus the index's ``model``, ``embedder``, ``metric``, and
            ``delta_version_indexed`` so callers can report
            freshness.

        Raises:
            FileNotFoundError: No index exists for the column.
        """  # noqa: DOC502 — bubble up from pql._vector.search
        from pointlessql.pql._vector import search

        return search(
            client=self._client,
            table=table,
            column=column,
            query=query,
            top_k=top_k,
            unreachable_msg=self._unreachable_msg(),
        )

    def update(
        self,
        target: str,
        *,
        set_clause: dict[str, str],
        where: str | None = None,
        track_value_changes: bool = False,
    ) -> dict[str, Any]:
        """Run ``UPDATE target SET ... WHERE ...`` against a Delta table.

        Wraps :meth:`deltalake.DeltaTable.update` with the audit
        machinery: every call emits one ``agent_run_operations``
        row when ``agent_run_id`` is set, captures
        delta_version_before/_after, and records ``rows_affected``
        from the deltalake metrics.  Optional CDF-based per-cell
        capture mirrors :meth:`merge`'s ``track_value_changes``
        opt-in.

        Args:
            target: Three-part name ``"catalog.schema.table"``.
            set_clause: Mapping ``column_name -> SQL-expression-string``.
                Passed verbatim to deltalake.  Empty dict raises
                :class:`ValueError`.
            where: SQL WHERE clause (delta-rs / DataFusion dialect)
                or ``None`` to update every row.
            track_value_changes: When ``True``, populate
                ``lineage_value_changes`` from the Delta CDF for
                this update's commit range.  CDF must already be
                enabled on the target — first writes via
                :meth:`write_table` enable it automatically.

        Returns:
            The deltalake metrics dict
            (``num_added_files``, ``num_removed_files``,
            ``num_updated_rows``, ``num_copied_rows``,
            ``execution_time_ms``, ``scan_time_ms``).
        """
        return update_table(
            client=self._client,
            full_name=target,
            set_clause=set_clause,
            where=where,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
            track_value_changes=track_value_changes,
        )

    def delete(
        self,
        target: str,
        *,
        where: str | None = None,
    ) -> dict[str, Any]:
        """Run ``DELETE FROM target WHERE ...`` against a Delta table.

        Wraps :meth:`deltalake.DeltaTable.delete`.  ``where=None``
        deletes every row — the SQL editor surface forces a
        confirmation modal in that case (Phase 63.7) but the
        primitive itself does not refuse the call.

        Args:
            target: Three-part name ``"catalog.schema.table"``.
            where: SQL WHERE clause (delta-rs / DataFusion dialect)
                or ``None`` for a full-table delete.

        Returns:
            The deltalake metrics dict
            (``num_added_files``, ``num_removed_files``,
            ``num_deleted_rows``, ``num_copied_rows``,
            ``execution_time_ms``, ``scan_time_ms``).
        """
        return delete_table_rows(
            client=self._client,
            full_name=target,
            where=where,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
        )

    def aggregate(
        self,
        source_df: Any,
        target: str,
        *,
        group_by: list[str],
        aggs: dict[str, AggSpec],
        source_table_fqn: str,
        mode: AggregateMode = "overwrite",
        derivations: Mapping[str, Sequence[str]] | None = None,
    ) -> dict[str, Any]:
        """Group-aggregate *source_df* into *target* with fan-in lineage.

        The third Medallion building block — bronze (``autoload``)
        feeds silver (``merge``) feeds gold (``aggregate``).  Earlier
        sprints used ``write_table(mode="overwrite")`` after a
        pandas ``groupby`` to materialise gold; that path silently
        dropped per-row lineage because the N-to-1 fan-in cannot
        carry through the merge ID-synthesis formula.  This primitive
        records one edge per (source row → target group) pair so
        's row-trace UI can surface the fan-in.

        ``source_table_fqn`` is **required** here (unlike the
        optional kwarg on :meth:`merge` and :meth:`write_table`):
        an aggregate without a declared upstream produces no useful
        lineage, so the primitive fails fast.

        Args:
            source_df: Source pandas DataFrame.  When the
                ``_lineage_row_id`` column is missing the
                aggregation still runs but emits zero edges.
            target: UC ``"catalog.schema.table"`` reference.  Created
                on first call when missing.
            group_by: Non-empty list of column names to group on.
                Every column must be present on *source_df*.
            aggs: Mapping ``output_col -> (source_col, agg_fn)`` —
                pandas-style named aggregations.  ``agg_fn`` is
                either a name string (``"sum"``, ``"mean"``, ...)
                or a callable.
            source_table_fqn: Required UC FQN of the upstream table
                that produced *source_df*.
            mode: ``"overwrite"`` (default) or ``"append"``.
            derivations: Optional declarative mapping of derived
                target columns (those produced by upstream
                ``.assign(...)``, arithmetic, or other DataFrame
                ops before this call) to their *true* source-column
                names.  populates ``derived`` rows
                in ``lineage_column_map`` so the column-trace UI
                can answer "where did ``placed_day`` come from?"
                even though the primitive itself only saw the
                already-derived column.

        Returns:
            ``{"target", "rows_written", "groups", "edges_emitted"}``.
        """
        return aggregate_table(
            client=self._client,
            engine=self._engine,
            source_df=source_df,
            target=target,
            group_by=group_by,
            aggs=aggs,
            source_table_fqn=source_table_fqn,
            mode=mode,
            unreachable_msg=self._unreachable_msg(),
            derivations=derivations,
            agent_run_id=self._current_run_id,
        )

    def autoload(
        self,
        source_path: str,
        target: str,
        *,
        source_system: str = "",
        file_format: AutoloadFormat = "auto",
        source_volume_fqn: str | None = None,
    ) -> dict[str, Any]:
        """Lift files from a Volume directory into a bronze Delta table.

        DuckDB type-infers each file
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
                or glob pattern.  Volumes-as-managed-directories;
                HTTP-fetched-Volume support is a follow-up.
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
            source_volume_fqn: Optional UC FQN of the upstream
                Volume backing *source_path*.  Stashed on the audit
                row today; future Volume-tracking work will surface
                it as an OpenLineage input.

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
            agent_run_id=self._current_run_id,
            source_volume_fqn=source_volume_fqn,
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

    def widgets(self) -> dict[str, Any]:
        """Return the resolved widget values for the active notebook.

        Phase 99 — kernel-side shim over the
        :mod:`pointlessql.services.notebook.widgets` resolver.  Reads
        the active notebook UUID from
        :func:`pointlessql.pql.context.current_notebook_id`; outside
        the notebook editor (interactive REPL, subprocess agent runs
        without the env-bridge) the call returns an empty dict so
        ``params = pql.widgets()`` is safe to write unconditionally.

        Returns:
            Mapping ``widget_name → value``.  Values flow from the
            ``notebook_widgets`` table — ``default_value`` overridden
            by anything the editor's widgets-panel submitted on the
            current execute (the WS bridge feeds the overrides into
            the metadata DB on Save; per-execute form-state overrides
            are not yet wired through the kernel context).  When no
            notebook context is active the mapping is empty.
        """
        from pointlessql.config import Settings
        from pointlessql.db import get_session_factory, init_db
        from pointlessql.pql.context import current_notebook_id
        from pointlessql.services.notebook.widgets import (
            resolve_widget_values,
        )

        notebook_id = current_notebook_id()
        if not notebook_id:
            return {}
        try:
            factory = get_session_factory()
        except RuntimeError:
            # Kernel subprocess bypasses the FastAPI lifespan; the
            # session factory is unbound on first widget read.
            # ``init_db`` is idempotent — re-running against the same
            # URL is a no-op after the first call.
            init_db(Settings().db.url)
            factory = get_session_factory()
        with factory() as session:
            return resolve_widget_values(session, notebook_id=notebook_id)
