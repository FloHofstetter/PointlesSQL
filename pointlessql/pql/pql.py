"""Sync bridge between Unity Catalog metadata and Delta Lake DataFrames.

The package is split into ``_types`` (SQLResult), ``_read``,
``_sql``, ``_write``, ``_list`` siblings.  The :class:`PQL` class
stays here as the public façade; method bodies delegate to the
sibling helpers so the orchestration shape (init → method dispatch)
is readable in one file while the per-concern logic lives next door.

``SQLResult`` is re-exported from this module so existing
``from pointlessql.pql.pql import SQLResult`` callers (notably the
test suite) continue to resolve unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from soyuz_catalog_client import Client

from pointlessql.pql._aggregate import AggregateMode, AggSpec, aggregate_table
from pointlessql.pql._autoload import AutoloadFormat, autoload_files
from pointlessql.pql._branch import (
    create_branch_schema,
    discard_branch_schema,
    preview_promote_conflicts,
    promote_branch_schema,
)
from pointlessql.pql._list import list_catalogs, list_schemas, list_tables
from pointlessql.pql._merge import MergeStrategy, merge_table
from pointlessql.pql._read import read_table
from pointlessql.pql._rollback import RollbackResult, rollback_table
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

    When the ``POINTLESSQL_PRINCIPAL`` environment variable is set
    and no explicit ``client`` is passed, the constructor builds a
    principal-forwarded client via ``make_principal_client()`` so
    every catalog call carries an ``X-Principal`` header.  The
    Papermill executor uses this to make notebook code that
    instantiates ``PQL()`` inherit the job's run-as user without
    any extra wiring — regular interactive use is unaffected.

    The constructor also accepts an explicit ``principal`` argument
    so a Hermes plugin (or any other process spawning PQL
    programmatically) can pass the agent's principal without
    mutating the process env.  Resolution order: explicit ``client``
    wins; otherwise an explicit ``principal`` argument; otherwise
    the ``POINTLESSQL_PRINCIPAL`` env var; otherwise an unforwarded
    client.

    Lazy metadata-DB initialisation: when the agent runtime spawns
    the ``.py`` as a subprocess the FastAPI lifespan never runs, so
    the audit-trail writes from :meth:`autoload` / :meth:`merge` /
    :meth:`write_table` would raise
    ``RuntimeError("Database not initialised — call init_db() first")``.
    If a run id is resolved (explicit ``agent_run_id`` or env) and
    the session factory is unbound, ``__init__`` lazy-calls
    :func:`pointlessql.db.init_db` against ``settings.db.url`` so
    agent-authored notebooks need no DB-init boilerplate.  The
    interactive path stays untouched because it is gated on
    ``self._current_run_id``.

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
        agent_run_id: Explicit run UUID; every PQL primitive call
            writes one ``agent_run_operations`` row for forced-audit
            purposes.  Wins over ``POINTLESSQL_AGENT_RUN_ID``;
            ``None`` keeps the interactive path silent.
    """

    def __init__(
        self,
        client: Client | None = None,
        settings: Settings | None = None,
        engine: Engine | str | None = None,
        *,
        principal: str | None = None,
        agent_run_id: str | None = None,
    ) -> None:
        resolved = settings or Settings()
        # Agent-run-id resolution mirrors `principal`.  Explicit
        # kwarg wins; otherwise the runtime sets the env var before
        # exec'ing the agent's `.py`.  ``None`` keeps the interactive
        # PQL path agnostic — no operation rows are emitted.
        self._current_run_id = agent_run_id or os.environ.get("POINTLESSQL_AGENT_RUN_ID")
        if client is not None:
            self._client = client
        else:
            effective = principal or os.environ.get("POINTLESSQL_PRINCIPAL")
            # Forward X-Agent-Run-Id outbound on every UC call so
            # soyuz's audit log (Sprint 14.4) can attribute the
            # mutation to the owning run.  ``None`` skips the header.
            if effective:
                self._client = make_principal_client(
                    resolved, effective, agent_run_id=self._current_run_id
                )
            else:
                self._client = make_soyuz_client(resolved, agent_run_id=self._current_run_id)
        if engine is None:
            self._engine = make_engine(resolved.delta.engine)
        elif isinstance(engine, str):
            self._engine = make_engine(engine)
        else:
            self._engine = engine
        # Subprocess-spawned agent notebooks bypass the FastAPI
        # lifespan, so ``get_session_factory()`` would raise on the
        # first ``agent_run_operations`` write.  Lazy-init the
        # metadata DB when a run id was resolved and no factory is
        # bound yet.  ``init_db`` is idempotent under repeated
        # invocations on the same URL — alembic upgrade-to-head is a
        # no-op once head is reached.
        if self._current_run_id:
            from pointlessql.db import get_session_factory, init_db

            try:
                get_session_factory()
            except RuntimeError:
                init_db(resolved.db.url)

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

    def table_at_version(self, full_name: str, version: int) -> Any:
        """Read a Delta table as of a specific historical version (Sprint 20.3).

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
            source_model_uri: Sprint 21.7 — optional registered-model
                URI ``models:/cat.sch.model/<version>`` declaring
                that *df* is the output of inference against a model.
                Stamps every row-edge with the model URI so the
                model-detail Lineage DAG can paint *full_name* as a
                downstream prediction node.
            derivations: Optional declarative mapping of derived
                target columns to their *true* source-column names
                (Sprint 15.6.2).  Effective only when
                ``source_table_fqn`` is also set.
        """
        write_table(
            client=self._client,
            engine=self._engine,
            df=df,
            full_name=full_name,
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
            source_model_uri: Sprint 21.8 — optional registered-model
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
                explain dropped rows (Sprint 15.5.3).  Default
                ``False`` keeps the cost off the hot path.
            track_value_changes: When ``True`` and
                ``strategy="upsert"``, read the Delta Change Data
                Feed for the merge's commit range and record one
                ``lineage_value_changes`` row per actually-different
                cell on a matched-and-updated target row (Sprint
                15.7.3).  Silently ignored on ``strategy="scd2"``.
                Default ``False`` keeps the CDF read off the hot
                path.
            derivations: Optional declarative mapping of derived
                target columns to their *true* source-column names
                (Sprint 15.6.2).  Lets the column-trace UI surface
                upstream-of-merge ``.assign(...)`` derivations.

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

    def training_context(
        self,
        *,
        framework: str = "auto",
        op_name: str = "train_model",
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Wrap a training block so MLflow autolog fires + audit row lands.

        Sprint 21.3 — agents call::

            with pql.training_context(framework="sklearn"):
                model.fit(X, y)

        The wrapper enables ``mlflow.autolog()`` for the requested
        framework, opens an MLflow run (or nests under an outer one),
        captures ``run.data.params + .metrics`` at exit, and stores
        the JSON-encoded snapshot on the audit operation row's
        ``training_params_json`` column. Best-effort: works without
        MLflow installed (audit row still lands, snapshot is empty).

        Args:
            framework: Hint for ``mlflow.autolog`` flavor; defaults to
                ``"auto"``.
            op_name: Audit-row label; defaults to ``"train_model"``.
            params: Optional initial params dict merged into the
                operation row.

        Returns:
            A context manager yielding a
            :class:`~pointlessql.services.agent_runs.training_context.TrainingRecorder`.
        """
        from pointlessql.db import get_session_factory
        from pointlessql.services.agent_runs.training_context import (
            training_context as _training_context,
        )

        factory = get_session_factory() if self._current_run_id else None
        return _training_context(
            factory,
            agent_run_id=self._current_run_id,
            framework=framework,
            op_name=op_name,
            params=dict(params) if params is not None else None,
        )

    def rollback(
        self,
        target: str,
        *,
        before_run: str,
        op_ordinal: int | None = None,
        allow_force: bool = False,
    ) -> RollbackResult:
        """Undo *before_run*'s write to *target* via Delta restore.

        Looks up the targeted operation by ``(before_run, target)``
        in ``agent_run_operations``, recovers its
        ``delta_version_before``, and atomically restores the Delta
        table to that version.  Rollback IS an operation: a fresh
        ``agent_run_operations`` row is emitted with
        ``op_name='rollback'`` so the audit trail records the undo
        alongside the original change.

        The four refusal modes are evaluated *before* the Delta
        state is mutated.  Pass ``op_ordinal`` to disambiguate runs
        that wrote *target* more than once; pass
        ``allow_force=True`` to suppress the staleness check when
        intervening writes by other runs would otherwise be
        silently overwritten.

        Args:
            target: UC ``"catalog.schema.table"`` reference.  Must
                already exist in soyuz-catalog.
            before_run: ``agent_runs.id`` of the run whose write
                to *target* should be undone.
            op_ordinal: Explicit ordinal of the op to rollback when
                the run touched *target* more than once.  ``None``
                works when exactly one op matches.
            allow_force: When ``True``, bypass the staleness check.
                Defaults to ``False`` so a casual click cannot
                silently overwrite intervening writes from other
                runs.

        Returns:
            A :class:`RollbackResult` with ``version_before``,
            ``version_after``, the historical
            ``target_version_restored``, and the
            ``restored_file_count`` reported by the deltalake
            metrics dict.
        """
        return rollback_table(
            client=self._client,
            target=target,
            before_run=before_run,
            unreachable_msg=self._unreachable_msg(),
            op_ordinal=op_ordinal,
            allow_force=allow_force,
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
        Sprint 15.5.2's row-trace UI can surface the fan-in.

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
                names.  Sprint 15.6.2 — populates ``derived`` rows
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

    def branch(
        self,
        source_schema: str,
        branch_name: str,
        *,
        strategy: Literal["auto", "symlink", "deep_copy"] = "auto",
    ) -> str:
        """Create a Delta branch of *source_schema* under *branch_name*.

        Phase 16.5.2 entry point.  Drops a fresh UC schema named
        ``catalog.branch_name`` (catalog is inherited from
        *source_schema*) whose Delta tables either symlink (local
        FS) or deep-copy (cloud, opt-in) the source's parquet files,
        then stamps the schema with ``pointlessql.branch.*`` tag
        metadata so subsequent ``pql.branch_discard`` /
        ``pql.branch_promote`` calls can find it.

        Writes against the branch (``pql.write_table``,
        ``pql.merge``, etc.) land in the branch's storage prefix and
        do not touch the parent — this is the isolation guarantee.

        Args:
            source_schema: Two-part ``catalog.schema`` of the parent.
            branch_name: Plain branch schema name (no dots).
            strategy: ``"auto"`` (recommended), ``"symlink"``, or
                ``"deep_copy"``.  ``"auto"`` resolves to symlink on
                local FS and to either deep-copy or
                :class:`BranchCloudUnsupportedError` on cloud
                storage, depending on
                ``settings.branch.cloud_strategy``.

        Returns:
            The branch's two-part FQN ``catalog.branch_name``.
        """
        return create_branch_schema(
            client=self._client,
            source_schema_fqn=source_schema,
            branch_name=branch_name,
            settings=Settings(),
            strategy=strategy,
            agent_run_id=self._current_run_id,
        )

    def branch_promote(self, branch_schema: str) -> dict[str, str]:
        """Promote a branch to be the new parent via UC pointer-swap.

        Phase 16.5.4 entry point.  Refuses promotion when the parent
        moved between branch creation and now (raises
        :class:`BranchPromotionConflictError`); recovery is to discard
        and re-branch.  v1 is pointer-swap-only — the parent is
        renamed to ``{parent}_pre_promote_<ts>`` (backup), the branch
        is renamed to the parent's old name, and tags are updated.

        Permission gate: caller is responsible for enforcing
        admin / supervisor scope before invoking.  The route handler
        in 16.5.5 wraps this with :func:`require_admin`.

        Args:
            branch_schema: Two-part ``catalog.branch_name``.

        Returns:
            ``{"new_parent": ..., "backup": ...}``.
        """
        return promote_branch_schema(
            client=self._client,
            branch_schema_fqn=branch_schema,
            settings=Settings(),
            agent_run_id=self._current_run_id,
        )

    def branch_promote_preview(self, branch_schema: str) -> dict[str, Any]:
        """Dry-run conflict-detection for a planned promotion.

        Returns ``{ok: bool, conflicts: list[...]}`` without mutating
        any UC state.  The Control-Room UI renders this directly so
        a reviewer sees the conflict-report before clicking promote.

        Args:
            branch_schema: Two-part ``catalog.branch_name``.

        Returns:
            Conflict report dict (see :func:`preview_promote_conflicts`).
        """
        return preview_promote_conflicts(
            client=self._client,
            branch_schema_fqn=branch_schema,
        )

    def branch_discard(self, branch_schema: str) -> None:
        """Permanently remove a Delta branch and its UC namespace.

        Phase 16.5.3 entry point.  Idempotent for already-discarded
        branches (no-op + warning log).  Refuses to discard a
        promoted branch — promotion is final.  Cleans up the local-
        FS storage tree without touching the source parquets that
        symlinks point at.

        Args:
            branch_schema: Two-part ``catalog.branch_name`` of the
                branch to remove.
        """
        discard_branch_schema(
            client=self._client,
            branch_schema_fqn=branch_schema,
            settings=Settings(),
            agent_run_id=self._current_run_id,
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
