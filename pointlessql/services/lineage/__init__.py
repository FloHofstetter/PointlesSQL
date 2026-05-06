"""Per-row, per-column, and per-cell lineage capture + walkback APIs.

The public surface — re-exported from
:mod:`pointlessql.services.lineage_edges` for backwards compatibility
— covers three orthogonal data streams:

* **Row-level** (:mod:`.rows`): edges + rejects + walkback.  Populated
  by ``pql.merge`` / ``pql.write_table`` / ``pql.aggregate``.
* **Column-level** (:mod:`.columns`): source-column → target-column
  mappings.  Populated by every PQL primitive plus the sqlglot AST
  walk in ``pql.sql``.
* **Value-level** (:mod:`.values`): per-cell preimage / postimage
  captures.  Populated by ``pql.merge(track_value_changes=True)`` via
  :mod:`pointlessql.services.value_change_capture`.

All inserts are best-effort — a DB hiccup must never roll back a
Delta write that already committed.  Failures are returned to the
caller as an ``Exception`` so the operation row can carry the
``[lineage_*_partial]`` markers for the audit trail.

Shared types, exceptions, constants, and helpers live in
:mod:`._types`.  Each callable lives in exactly one workflow module.
"""

from __future__ import annotations

from pointlessql.services.lineage._types import (
    MAX_COLUMN_EDGES_PER_OP,
    MAX_VALUE_CHANGES_PER_OP,
    ColumnEdgeCapExceeded,
    ColumnEdgeSpec,
    ColumnPredecessorRef,
    ColumnTraceStep,
    LineageStep,
    PredecessorRef,
    ValueChangeCapExceeded,
    ValueChangeSpec,
    synth_aggregate_target_row_id,
    synth_target_row_id,
)
from pointlessql.services.lineage.columns import (
    count_column_edges_for_op,
    fetch_target_column_predecessors,
    record_column_edges,
    walk_back_columns,
)
from pointlessql.services.lineage.rows import (
    count_edges_for_op,
    fetch_source_row_descendants,
    fetch_target_row_predecessors,
    lookup_bronze_source_file,
    record_edges,
    record_rejects,
    walk_back,
)
from pointlessql.services.lineage.values import (
    count_value_changes_for_op,
    fetch_value_changes_for_row,
    record_value_changes,
)

__all__ = [
    "MAX_COLUMN_EDGES_PER_OP",
    "MAX_VALUE_CHANGES_PER_OP",
    "ColumnEdgeCapExceeded",
    "ColumnEdgeSpec",
    "ColumnPredecessorRef",
    "ColumnTraceStep",
    "LineageStep",
    "PredecessorRef",
    "ValueChangeCapExceeded",
    "ValueChangeSpec",
    "count_column_edges_for_op",
    "count_edges_for_op",
    "count_value_changes_for_op",
    "fetch_source_row_descendants",
    "fetch_target_column_predecessors",
    "fetch_target_row_predecessors",
    "fetch_value_changes_for_row",
    "lookup_bronze_source_file",
    "record_column_edges",
    "record_edges",
    "record_rejects",
    "record_value_changes",
    "synth_aggregate_target_row_id",
    "synth_target_row_id",
    "walk_back",
    "walk_back_columns",
]
