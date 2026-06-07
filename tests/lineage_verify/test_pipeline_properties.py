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
from tests.lineage_verify._harness import run_sql_then_write_op, run_write_op
from tests.lineage_verify.strategies import (
    SqlPipeline,
    WritePipeline,
    sql_pipelines,
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
