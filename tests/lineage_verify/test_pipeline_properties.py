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
from tests.lineage_verify._harness import run_write_op
from tests.lineage_verify.strategies import WritePipeline, write_pipelines


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
