"""Pure invariant checkers for lineage correctness.

Each checker is ``(facts: OperationFacts) -> list[Violation]`` with no I/O.
They formalise the invariants in
``docs/internal/lineage-invariants.md``; :func:`verify_operation` runs all
of them.  The inputs are plain value snapshots so the same checkers verify
Hypothesis-generated pipelines, the golden corpus, and real recorded rows
adapted into :class:`OperationFacts`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.services.lineage._types import (
    synth_target_row_id,
)

# Allowed enums, mirrored from the ORM CHECK constraints so a checker fails
# if a writer ever emits an out-of-band value.
_REJECT_REASONS = frozenset(
    {
        "on_key_null",
        "schema_mismatch",
        "duplicate_in_source",
        "merge_predicate_excluded",
        "other",
        "expectation_failed",
    }
)
# transform_detail markers that excuse an ``unknown_origin`` column from the
# coverage requirement (an injected audit column or the synthesised row id).
_EXEMPT_DETAILS = frozenset({"audit", "synth_target_row_id"})


@dataclass(frozen=True)
class Violation:
    """One invariant breach, with the invariant id + a human message."""

    invariant: str
    message: str


@dataclass(frozen=True)
class RowEdgeFact:
    """A recorded ``LineageRowEdge`` (the fields the invariants read)."""

    source_row_id: str
    target_row_id: str


@dataclass(frozen=True)
class RejectFact:
    """A recorded ``LineageRowReject``."""

    source_row_id: str
    reason: str


@dataclass(frozen=True)
class ColumnMapFact:
    """A recorded ``LineageColumnMap`` entry."""

    target_column: str
    transform_kind: str
    transform_detail: str | None = None
    source_table: str | None = None
    source_column: str | None = None


@dataclass(frozen=True)
class ValueChangeFact:
    """A recorded ``LineageValueChange``."""

    target_row_id: str
    target_column: str
    old_value: str | None
    new_value: str | None


def _str_list() -> list[str]:
    return []


def _edge_list() -> list[RowEdgeFact]:
    return []


def _reject_list() -> list[RejectFact]:
    return []


def _colmap_list() -> list[ColumnMapFact]:
    return []


def _value_change_list() -> list[ValueChangeFact]:
    return []


@dataclass(frozen=True)
class OperationFacts:
    """A pure snapshot of one lineage-bearing operation.

    Attributes:
        target_table: FQN the operation wrote.
        source_row_ids: ``_lineage_row_id`` of each input row (``""`` when a
            row carried none).
        target_row_ids: ``_lineage_row_id`` of each output row.
        output_columns: the output table's column names.
        edges: the ``LineageRowEdge`` rows the operation recorded.
        rejects: the ``LineageRowReject`` rows the operation recorded.
        column_map: the ``LineageColumnMap`` rows the operation recorded.
        value_changes: the ``LineageValueChange`` rows the operation recorded.
        aggregate: whether the operation collapses rows (an aggregate), in
            which case target ids use the aggregate-synthesis formula and the
            1:1 determinism check (INV-2) does not apply.
    """

    target_table: str
    source_row_ids: list[str] = field(default_factory=_str_list)
    target_row_ids: list[str] = field(default_factory=_str_list)
    output_columns: list[str] = field(default_factory=_str_list)
    edges: list[RowEdgeFact] = field(default_factory=_edge_list)
    rejects: list[RejectFact] = field(default_factory=_reject_list)
    column_map: list[ColumnMapFact] = field(default_factory=_colmap_list)
    value_changes: list[ValueChangeFact] = field(default_factory=_value_change_list)
    aggregate: bool = False

    @property
    def lineage_bearing(self) -> bool:
        """True when any input row carried a ``_lineage_row_id``."""
        return any(bool(s) for s in self.source_row_ids)


def check_row_edge_closure(facts: OperationFacts) -> list[Violation]:
    """INV-1: lineage-bearing output rows trace back, or are rejected.

    Catches the 15.8 failure mode (a SELECT that drops ``_lineage_row_id``
    from a lineage-bearing source) as a hard violation, plus the general
    closure property.
    """
    out: list[Violation] = []
    if not facts.lineage_bearing:
        return out
    if LINEAGE_ROW_ID_COLUMN not in facts.output_columns:
        out.append(
            Violation(
                "INV-1",
                f"lineage-bearing write to {facts.target_table!r} dropped "
                f"{LINEAGE_ROW_ID_COLUMN!r} from its output; downstream row "
                "edges will be skipped",
            )
        )
        return out
    rejected = {r.source_row_id for r in facts.rejects}
    edge_targets = {e.target_row_id for e in facts.edges}
    edge_sources = {e.source_row_id for e in facts.edges}
    for tid in facts.target_row_ids:
        if tid and tid not in edge_targets:
            out.append(
                Violation(
                    "INV-1",
                    f"output row {tid!r} in {facts.target_table!r} has no "
                    "row-edge back to a source",
                )
            )
    for sid in facts.source_row_ids:
        if sid and sid not in edge_sources and sid not in rejected:
            out.append(
                Violation(
                    "INV-1",
                    f"source row {sid!r} neither produced an edge nor a reject",
                )
            )
    return out


def check_target_id_synthesis(facts: OperationFacts) -> list[Violation]:
    """INV-2: each edge's target id is the canonical deterministic synthesis."""
    out: list[Violation] = []
    if facts.aggregate:
        # Aggregate targets use the group-key synthesis; the 1:1 formula does
        # not apply, so this invariant is checked only for row-pass-through.
        return out
    for edge in facts.edges:
        expected = synth_target_row_id(edge.source_row_id, facts.target_table)
        if edge.target_row_id != expected:
            out.append(
                Violation(
                    "INV-2",
                    f"edge {edge.source_row_id!r}->{edge.target_row_id!r} "
                    f"target id is not synth_target_row_id (expected {expected!r})",
                )
            )
    return out


def check_edge_endpoints(facts: OperationFacts) -> list[Violation]:
    """INV-3: every edge endpoint references a real input/output row."""
    out: list[Violation] = []
    src = {s for s in facts.source_row_ids if s}
    tgt = {t for t in facts.target_row_ids if t}
    for edge in facts.edges:
        if edge.source_row_id not in src:
            out.append(
                Violation(
                    "INV-3",
                    f"edge source {edge.source_row_id!r} is not one of the operation's input rows",
                )
            )
        if edge.target_row_id not in tgt:
            out.append(
                Violation(
                    "INV-3",
                    f"edge target {edge.target_row_id!r} is not one of the operation's output rows",
                )
            )
    return out


def check_column_map_coverage(facts: OperationFacts) -> list[Violation]:
    """INV-4: every non-constant output column is traceable in the column map."""
    out: list[Violation] = []
    by_target: dict[str, list[ColumnMapFact]] = {}
    for entry in facts.column_map:
        by_target.setdefault(entry.target_column, []).append(entry)
    for col in facts.output_columns:
        if col == LINEAGE_ROW_ID_COLUMN:
            continue
        entries = by_target.get(col, [])
        if not entries:
            out.append(Violation("INV-4", f"output column {col!r} has no column-map entry"))
            continue
        traceable = any(e.transform_kind != "unknown_origin" for e in entries)
        exempt = any(
            e.transform_kind == "unknown_origin" and e.transform_detail in _EXEMPT_DETAILS
            for e in entries
        )
        if not traceable and not exempt:
            out.append(
                Violation(
                    "INV-4",
                    f"output column {col!r} maps only as unknown_origin without "
                    "an audit/synth marker",
                )
            )
    return out


def check_value_changes_real(facts: OperationFacts) -> list[Violation]:
    """INV-5: value-changes target real output rows and record real changes."""
    out: list[Violation] = []
    tgt = {t for t in facts.target_row_ids if t}
    for vc in facts.value_changes:
        if vc.target_row_id not in tgt:
            out.append(
                Violation(
                    "INV-5",
                    f"value-change targets unknown row {vc.target_row_id!r}",
                )
            )
        if vc.old_value == vc.new_value:
            out.append(
                Violation(
                    "INV-5",
                    f"value-change on column {vc.target_column!r} row "
                    f"{vc.target_row_id!r} records no actual change (old == new)",
                )
            )
    return out


def check_reject_reasons(facts: OperationFacts) -> list[Violation]:
    """INV-6: reject reasons are valid and a row is never both kept + rejected."""
    out: list[Violation] = []
    edge_sources = {e.source_row_id for e in facts.edges}
    for reject in facts.rejects:
        if reject.reason not in _REJECT_REASONS:
            out.append(Violation("INV-6", f"reject reason {reject.reason!r} is not allowed"))
        if reject.source_row_id in edge_sources:
            out.append(
                Violation(
                    "INV-6",
                    f"source row {reject.source_row_id!r} is both edged and rejected",
                )
            )
    return out


def verify_operation(facts: OperationFacts) -> list[Violation]:
    """Run every invariant checker and return all violations.

    The single entry point the property suite, golden corpus and CI marker
    call.  An empty list means the operation's lineage is correct.
    """
    violations: list[Violation] = []
    violations.extend(check_row_edge_closure(facts))
    violations.extend(check_target_id_synthesis(facts))
    violations.extend(check_edge_endpoints(facts))
    violations.extend(check_column_map_coverage(facts))
    violations.extend(check_value_changes_real(facts))
    violations.extend(check_reject_reasons(facts))
    return violations
