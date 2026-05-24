# pyright: reportUnusedClass=false
"""Group-aggregate for the PQL façade — gold-layer fan-in lineage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pointlessql.pql._aggregate import AggregateMode, AggSpec, aggregate_table
from pointlessql.pql._pql_base import PQLBase as _PQLBase


class _AggregateMixin(_PQLBase):
    """Group-aggregate a frame into a Delta target with fan-in lineage."""

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
