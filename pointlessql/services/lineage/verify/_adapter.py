"""Adapter from recorded lineage rows to a pure ``OperationFacts`` snapshot.

Maps the four ORM-shaped lineage row collections (row edges, rejects,
column-map entries, value changes) plus the operation's input/output row
populations into the pure :class:`OperationFacts` the invariant checkers
consume.

It is defined over structural protocols rather than the ORM models so the
``verify`` package stays import-pure (no SQLAlchemy dependency) and the same
adapter serves the property suite, the golden corpus, and a future runtime
self-check.  The row populations (``source_row_ids`` / ``output_row_ids`` /
``output_columns``) are passed in by the caller because the lineage tables
record only edged and rejected rows — not the full input/output populations
the closure invariants need.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pointlessql.services.lineage.verify._invariants import (
    ColumnMapFact,
    OperationFacts,
    RejectFact,
    RowEdgeFact,
    ValueChangeFact,
)


class _EdgeRow(Protocol):
    """Structural shape of a recorded ``LineageRowEdge`` row."""

    source_row_id: str
    target_row_id: str


class _RejectRow(Protocol):
    """Structural shape of a recorded ``LineageRowReject`` row."""

    source_row_id: str
    reason: str


class _ColumnMapRow(Protocol):
    """Structural shape of a recorded ``LineageColumnMap`` row."""

    target_column: str
    transform_kind: str
    transform_detail: str | None
    source_table: str | None
    source_column: str | None


class _ValueChangeRow(Protocol):
    """Structural shape of a recorded ``LineageValueChange`` row."""

    target_row_id: str
    target_column: str
    old_value: str | None
    new_value: str | None


def facts_from_rows(
    *,
    target_table: str,
    source_row_ids: Sequence[str],
    output_columns: Sequence[str],
    output_row_ids: Sequence[str],
    edge_rows: Sequence[_EdgeRow],
    reject_rows: Sequence[_RejectRow] = (),
    colmap_rows: Sequence[_ColumnMapRow] = (),
    value_rows: Sequence[_ValueChangeRow] = (),
    aggregate: bool = False,
) -> OperationFacts:
    """Assemble an :class:`OperationFacts` from recorded rows and row populations.

    Args:
        target_table: Fully-qualified name the operation wrote.
        source_row_ids: ``_lineage_row_id`` of every input row (``""`` for a
            row that carried none).  The full source population, not just the
            edged subset.
        output_columns: The output table's column names.
        output_row_ids: ``_lineage_row_id`` of every output row.  The full
            target population, not just the edged subset.
        edge_rows: Recorded row-edge rows (``source_row_id`` / ``target_row_id``).
        reject_rows: Recorded reject rows (``source_row_id`` / ``reason``).
        colmap_rows: Recorded column-map rows.
        value_rows: Recorded value-change rows.
        aggregate: Whether the operation collapses rows (an aggregate), so the
            1:1 target-id determinism check does not apply.

    Returns:
        A pure snapshot the invariant checkers in
        :mod:`pointlessql.services.lineage.verify._invariants` can verify.
    """
    return OperationFacts(
        target_table=target_table,
        source_row_ids=list(source_row_ids),
        target_row_ids=list(output_row_ids),
        output_columns=list(output_columns),
        edges=[RowEdgeFact(e.source_row_id, e.target_row_id) for e in edge_rows],
        rejects=[RejectFact(r.source_row_id, r.reason) for r in reject_rows],
        column_map=[
            ColumnMapFact(
                target_column=c.target_column,
                transform_kind=c.transform_kind,
                transform_detail=c.transform_detail,
                source_table=c.source_table,
                source_column=c.source_column,
            )
            for c in colmap_rows
        ],
        value_changes=[
            ValueChangeFact(
                target_row_id=v.target_row_id,
                target_column=v.target_column,
                old_value=v.old_value,
                new_value=v.new_value,
            )
            for v in value_rows
        ],
        aggregate=aggregate,
    )
