"""Tests for the lineage-correctness invariant checkers.

Pins each invariant in ``docs/internal/lineage-invariants.md`` via the pure
checkers, including the deliberately re-introduced 15.8 failure mode (a
SELECT that drops ``_lineage_row_id``) which must make the suite — not just
an INFO log — fail.
"""

from __future__ import annotations

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.services.lineage._types import synth_target_row_id
from pointlessql.services.lineage.verify import (
    ColumnMapFact,
    OperationFacts,
    RejectFact,
    RowEdgeFact,
    ValueChangeFact,
    check_column_map_coverage,
    check_edge_endpoints,
    check_reject_reasons,
    check_row_edge_closure,
    check_target_id_synthesis,
    check_value_changes_real,
    verify_operation,
)

_TGT = "demo_ml.silver.houses"


def _clean_facts() -> OperationFacts:
    """A correct 2-row pass-through write: ids synthesised, edges complete."""
    src_ids = ["bronze-row-1", "bronze-row-2"]
    tgt_ids = [synth_target_row_id(s, _TGT) for s in src_ids]
    return OperationFacts(
        target_table=_TGT,
        source_row_ids=src_ids,
        target_row_ids=tgt_ids,
        output_columns=["house_id", "size_sqft", LINEAGE_ROW_ID_COLUMN],
        edges=[RowEdgeFact(s, t) for s, t in zip(src_ids, tgt_ids, strict=True)],
        column_map=[
            ColumnMapFact("house_id", "identity", source_column="house_id"),
            ColumnMapFact("size_sqft", "identity", source_column="size_sqft"),
        ],
    )


def test_clean_operation_has_no_violations() -> None:
    assert verify_operation(_clean_facts()) == []


# --- INV-1 row-edge closure (incl. the 15.8 bug) ---------------------------


def test_inv1_dropped_lineage_row_id_is_a_violation() -> None:
    """The real 15.8 bug: a lineage-bearing write that drops the id column."""
    facts = _clean_facts()
    broken = OperationFacts(
        target_table=facts.target_table,
        source_row_ids=facts.source_row_ids,
        target_row_ids=[],  # the SELECT dropped the column, so no target ids
        output_columns=["house_id", "size_sqft"],  # _lineage_row_id gone
        edges=[],
    )
    issues = check_row_edge_closure(broken)
    assert any(i.invariant == "INV-1" and "dropped" in i.message for i in issues)
    # and it surfaces through the aggregate entry point too
    assert verify_operation(broken)


def test_inv1_output_row_without_edge() -> None:
    facts = _clean_facts()
    facts.edges.pop()  # one output row now has no inbound edge
    issues = check_row_edge_closure(facts)
    assert any(i.invariant == "INV-1" and "row-edge" in i.message for i in issues)


def test_inv1_source_without_edge_or_reject() -> None:
    src_ids = ["s1"]
    facts = OperationFacts(
        target_table=_TGT,
        source_row_ids=src_ids,
        target_row_ids=[synth_target_row_id("s1", _TGT)],
        output_columns=[LINEAGE_ROW_ID_COLUMN],
        edges=[],  # s1 neither edged nor rejected
    )
    issues = check_row_edge_closure(facts)
    assert any("neither produced an edge nor a reject" in i.message for i in issues)


def test_inv1_rejected_source_is_clean() -> None:
    facts = OperationFacts(
        target_table=_TGT,
        source_row_ids=["s1"],
        target_row_ids=[],
        output_columns=[LINEAGE_ROW_ID_COLUMN],
        edges=[],
        rejects=[RejectFact("s1", "on_key_null")],
    )
    assert check_row_edge_closure(facts) == []


def test_inv1_non_lineage_bearing_is_exempt() -> None:
    facts = OperationFacts(
        target_table=_TGT,
        source_row_ids=["", ""],  # no source carried a row id
        output_columns=["a"],
    )
    assert check_row_edge_closure(facts) == []


# --- INV-2 target-id determinism -------------------------------------------


def test_inv2_wrong_target_id() -> None:
    facts = _clean_facts()
    facts.edges[0] = RowEdgeFact(facts.edges[0].source_row_id, "deadbeef")
    issues = check_target_id_synthesis(facts)
    assert any(i.invariant == "INV-2" for i in issues)


def test_inv2_skipped_for_aggregates() -> None:
    facts = OperationFacts(
        target_table=_TGT,
        source_row_ids=["s1", "s2"],
        target_row_ids=["agg-1"],
        output_columns=[LINEAGE_ROW_ID_COLUMN],
        edges=[RowEdgeFact("s1", "agg-1"), RowEdgeFact("s2", "agg-1")],
        aggregate=True,
    )
    # aggregate ids do not use the 1:1 formula → INV-2 must not fire
    assert check_target_id_synthesis(facts) == []


# --- INV-3 endpoints -------------------------------------------------------


def test_inv3_edge_endpoint_not_a_real_row() -> None:
    facts = _clean_facts()
    facts.edges.append(RowEdgeFact("ghost-source", "ghost-target"))
    issues = check_edge_endpoints(facts)
    assert sum(1 for i in issues if i.invariant == "INV-3") >= 2


# --- INV-4 column-map coverage ---------------------------------------------


def test_inv4_uncovered_output_column() -> None:
    facts = _clean_facts()
    facts.output_columns.append("orphan_col")
    issues = check_column_map_coverage(facts)
    assert any("orphan_col" in i.message for i in issues)


def test_inv4_audit_column_is_exempt() -> None:
    facts = _clean_facts()
    facts.output_columns.append("_ingested_at")
    facts.column_map.append(
        ColumnMapFact("_ingested_at", "unknown_origin", transform_detail="audit")
    )
    assert check_column_map_coverage(facts) == []


def test_inv4_lineage_row_id_column_is_exempt() -> None:
    # _lineage_row_id itself needs no column-map entry.
    assert check_column_map_coverage(_clean_facts()) == []


# --- INV-5 value-changes ---------------------------------------------------


def test_inv5_change_on_unknown_row() -> None:
    facts = _clean_facts()
    facts.value_changes.append(ValueChangeFact("nope", "size_sqft", "1", "2"))
    issues = check_value_changes_real(facts)
    assert any("unknown row" in i.message for i in issues)


def test_inv5_noop_change() -> None:
    facts = _clean_facts()
    facts.value_changes.append(
        ValueChangeFact(facts.target_row_ids[0], "size_sqft", "5", "5")
    )
    issues = check_value_changes_real(facts)
    assert any("no actual change" in i.message for i in issues)


# --- INV-6 reject reasons --------------------------------------------------


def test_inv6_bad_reason() -> None:
    facts = OperationFacts(
        target_table=_TGT,
        source_row_ids=["s1"],
        rejects=[RejectFact("s1", "because_i_said_so")],
    )
    issues = check_reject_reasons(facts)
    assert any("not allowed" in i.message for i in issues)


def test_inv6_row_both_edged_and_rejected() -> None:
    facts = _clean_facts()
    facts.rejects.append(RejectFact(facts.edges[0].source_row_id, "on_key_null"))
    issues = check_reject_reasons(facts)
    assert any("both edged and rejected" in i.message for i in issues)
