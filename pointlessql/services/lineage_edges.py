"""Backward-compat re-export shim for the lineage capture API.

Implementation moved to :mod:`pointlessql.services.lineage`
(split per stream: :mod:`._types`, :mod:`.rows`, :mod:`.columns`,
:mod:`.values`).

Old import paths keep working — every public symbol that callers
imported from ``pointlessql.services.lineage_edges`` is re-exported
from the new subpackage.
"""

from __future__ import annotations

from pointlessql.services.lineage import (
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
    count_column_edges_for_op,
    count_edges_for_op,
    count_value_changes_for_op,
    fetch_source_row_descendants,
    fetch_target_column_predecessors,
    fetch_target_row_predecessors,
    fetch_value_changes_for_row,
    lookup_bronze_source_file,
    record_column_edges,
    record_edges,
    record_rejects,
    record_value_changes,
    synth_aggregate_target_row_id,
    synth_target_row_id,
    walk_back,
    walk_back_columns,
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
