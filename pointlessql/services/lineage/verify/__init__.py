"""Lineage-correctness verification engine — pure invariant checkers.

Formalises the row/column/value lineage invariants
([`docs/internal/lineage-invariants.md`](../../../../docs/internal/lineage-invariants.md))
as pure functions over an :class:`OperationFacts` snapshot — no I/O, fully
unit-testable.  The property suite (Hypothesis), the golden corpus, and
(adapted) real recorded rows all verify the *same* definition through
:func:`verify_operation`.

This is the core the rest of the engine feeds: generators + corpus build
``OperationFacts`` and assert ``verify_operation`` finds no violations.
"""

from __future__ import annotations

from pointlessql.services.lineage.verify._adapter import facts_from_rows
from pointlessql.services.lineage.verify._invariants import (
    ColumnMapFact,
    OperationFacts,
    RejectFact,
    RowEdgeFact,
    ValueChangeFact,
    Violation,
    check_column_map_coverage,
    check_edge_endpoints,
    check_reject_reasons,
    check_row_edge_closure,
    check_target_id_synthesis,
    check_value_changes_real,
    verify_operation,
)

__all__ = [
    "ColumnMapFact",
    "OperationFacts",
    "RejectFact",
    "RowEdgeFact",
    "ValueChangeFact",
    "Violation",
    "check_column_map_coverage",
    "check_edge_endpoints",
    "check_reject_reasons",
    "check_row_edge_closure",
    "check_target_id_synthesis",
    "check_value_changes_real",
    "facts_from_rows",
    "verify_operation",
]
