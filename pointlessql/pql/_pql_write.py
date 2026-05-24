# pyright: reportUnusedClass=false
"""Delta write + merge for the PQL façade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pointlessql.pql._merge import MergeStrategy, merge_table
from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._write import write_table


class _WriteMixin(_PQLBase):
    """Write to and merge into Delta tables registered in Unity Catalog."""

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
                through ``self.table()`` when a string).
            target: UC ``"catalog.schema.table"`` reference.  Must
                already exist — use :meth:`write_table` or
                ``self.autoload()`` to bootstrap.
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
