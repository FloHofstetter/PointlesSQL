"""Property: every lineage-bearing write satisfies all lineage invariants.

Generates arbitrary valid frames, runs them through the real ``write_table``
primitive, and asserts the recorded row-edges / column-map / target-id
synthesis satisfy ``verify_operation``.  A regression in propagation,
synthesis, or column-map coverage surfaces as a shrunk minimal counter-
example rather than a silent gap.  Per-operator depth (sql / merge /
aggregate / update) lands in the W3 waves.
"""

from __future__ import annotations

import pytest
from hypothesis import given

from pointlessql.services.lineage.verify import verify_operation
from tests.lineage_verify._harness import (
    run_aggregate_op,
    run_merge_op,
    run_sql_then_write_op,
    run_update_op,
    run_write_op,
)
from tests.lineage_verify.strategies import (
    AggregatePipeline,
    MergePipeline,
    SqlPipeline,
    UpdatePipeline,
    WritePipeline,
    aggregate_pipelines,
    merge_pipelines,
    sql_pipelines,
    update_pipelines,
    write_pipelines,
)


@pytest.mark.lineage_verify
@given(pipeline=write_pipelines())
def test_write_table_lineage_holds_all_invariants(pipeline: WritePipeline) -> None:
    facts = run_write_op(
        frame=pipeline.frame,
        source_fqn=pipeline.source_fqn,
        table_name=pipeline.table_name,
    )
    violations = verify_operation(facts)
    assert violations == [], [f"{v.invariant}: {v.message}" for v in violations]


@pytest.mark.lineage_verify
@given(pipeline=merge_pipelines())
def test_merge_lineage_holds_all_invariants(pipeline: MergePipeline) -> None:
    """An upsert merge edges every matched row, rejects null/dup keys, and the

    recorded value-changes are real — all invariants hold (INV-1/2/3/5/6).
    """
    facts = run_merge_op(
        base_frame=pipeline.base_frame,
        merge_frame=pipeline.merge_frame,
        on=pipeline.on,
        table_name=pipeline.table_name,
    )
    violations = verify_operation(facts)
    assert violations == [], [f"{v.invariant}: {v.message}" for v in violations]


@pytest.mark.lineage_verify
@given(pipeline=aggregate_pipelines())
def test_aggregate_fanin_lineage_holds_all_invariants(pipeline: AggregatePipeline) -> None:
    """A group-aggregate fans every source row into its group target.

    Each source row edges to its group's synthesised target id (N:1), every
    group target has at least one edge, and the 1:1 determinism check (INV-2)
    is correctly skipped for the aggregate boundary.
    """
    facts = run_aggregate_op(
        source_frame=pipeline.source_frame,
        group_by=pipeline.group_by,
        aggs=pipeline.aggs,
        table_name=pipeline.table_name,
    )
    violations = verify_operation(facts)
    assert violations == [], [f"{v.invariant}: {v.message}" for v in violations]


@pytest.mark.lineage_verify
@given(pipeline=update_pipelines())
def test_update_value_changes_are_real(pipeline: UpdatePipeline) -> None:
    """An in-place UPDATE records value-changes that are real, on real rows.

    The update is not cross-table lineage (no row-edges or column-map owed),
    so only INV-5 applies; every captured change must have old != new and
    target a row in the output.
    """
    facts = run_update_op(
        base_frame=pipeline.base_frame,
        set_clause=pipeline.set_clause,
        table_name=pipeline.table_name,
    )
    violations = verify_operation(facts)
    assert violations == [], [f"{v.invariant}: {v.message}" for v in violations]
    assert facts.value_changes, "expected the UPDATE to capture value-changes via CDF"


@pytest.mark.lineage_verify
@given(pipeline=sql_pipelines())
def test_sql_projection_preserves_lineage(pipeline: SqlPipeline) -> None:
    """A SELECT that omits _lineage_row_id still yields a fully-edged write.

    Pins the 15.8 fix: auto-projection carries the column through a
    row-preserving projection, so the downstream silver write traces every
    bronze row.
    """
    facts = run_sql_then_write_op(
        bronze_frame=pipeline.bronze_frame,
        select_columns=pipeline.select_columns,
        table_name=pipeline.table_name,
    )
    violations = verify_operation(facts)
    assert violations == [], [f"{v.invariant}: {v.message}" for v in violations]


@pytest.mark.lineage_verify
@given(pipeline=sql_pipelines())
def test_disabling_autoprojection_is_caught_as_a_drop(pipeline: SqlPipeline) -> None:
    """The deliberately re-introduced 15.8 drop fails the suite, not just a log.

    With auto-projection disabled, the silver write drops _lineage_row_id
    from a lineage-bearing source — exactly the original bug — and the
    invariant checker must flag it (INV-1), proving the engine catches the
    regression rather than only logging it.
    """
    facts = run_sql_then_write_op(
        bronze_frame=pipeline.bronze_frame,
        select_columns=pipeline.select_columns,
        table_name=pipeline.table_name,
        preserve_lineage_row_id=False,
    )
    violations = verify_operation(facts)
    assert any(v.invariant == "INV-1" and "dropped" in v.message for v in violations)
