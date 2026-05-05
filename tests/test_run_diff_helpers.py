"""Phase 18.9 — cell-level + column-lineage edge diff helpers.

Direct unit tests against
:func:`pointlessql.services.run_diff.build_value_changes_diff` and
:func:`build_column_lineage_diff` without the FastAPI route layer.
The fixtures seed two synthetic runs with overlapping but
divergent ``lineage_value_changes`` and ``lineage_column_map``
rows so each axis (divergent / a_only / b_only / kind_changed /
detail_changed) gets at least one assertion.
"""

from __future__ import annotations

import datetime as dt

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageColumnMap,
    LineageValueChange,
)
from pointlessql.services import run_diff


def _seed_run_with_op(*, run_id: str) -> int:
    """Insert ``AgentRun`` + one ``AgentRunOperation`` row, return op_id."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="diff@test.com",
                agent_id="differ",
                notebook_path="diff/job.py",
                source_snapshot_sha="0" * 64,
                status="succeeded",
                started_at=dt.datetime.now(dt.UTC),
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.t",
            input_sha=None,
            rows_affected=1,
            delta_version_before=0,
            delta_version_after=1,
            started_at=dt.datetime.now(dt.UTC),
            finished_at=dt.datetime.now(dt.UTC),
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return int(op.id)


def _add_value_change(
    *,
    run_id: str,
    op_id: int,
    table: str,
    row_id: str,
    column: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table=table,
                target_row_id=row_id,
                target_column=column,
                old_value=old_value,
                new_value=new_value,
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def _add_column_edge(
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    transform_kind: str = "identity",
    transform_detail: str | None = None,
) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table=source_table,
                source_column=source_column,
                target_table=target_table,
                target_column=target_column,
                transform_kind=transform_kind,
                transform_detail=transform_detail,
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()


def test_value_changes_diff_buckets_divergent_and_unique() -> None:
    """Diff isolates divergent vs only-in-a vs only-in-b cells."""
    op_a = _seed_run_with_op(run_id="aaaa1111-aaaa-1111-aaaa-111111111111")
    _seed_run_with_op(run_id="bbbb2222-bbbb-2222-bbbb-222222222222")

    # Same cell, different new_value → divergent.
    _add_value_change(
        run_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        op_id=op_a,
        table="main.silver.t",
        row_id="r1",
        column="amount",
        old_value="5",
        new_value="6",
    )
    _add_value_change(
        run_id="bbbb2222-bbbb-2222-bbbb-222222222222",
        op_id=op_a,  # SAME op_id so identity matches
        table="main.silver.t",
        row_id="r1",
        column="amount",
        old_value="5",
        new_value="7",
    )
    # Cell only in A.
    _add_value_change(
        run_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        op_id=op_a,
        table="main.silver.t",
        row_id="r2",
        column="amount",
        old_value=None,
        new_value="9",
    )
    # Cell only in B.
    _add_value_change(
        run_id="bbbb2222-bbbb-2222-bbbb-222222222222",
        op_id=op_a,
        table="main.silver.t",
        row_id="r3",
        column="amount",
        old_value=None,
        new_value="13",
    )
    # Same cell, identical new_value → must NOT appear.
    _add_value_change(
        run_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        op_id=op_a,
        table="main.silver.t",
        row_id="r4",
        column="amount",
        old_value=None,
        new_value="100",
    )
    _add_value_change(
        run_id="bbbb2222-bbbb-2222-bbbb-222222222222",
        op_id=op_a,
        table="main.silver.t",
        row_id="r4",
        column="amount",
        old_value=None,
        new_value="100",
    )

    diff = run_diff.build_value_changes_diff(
        app.state.session_factory,
        run_a_id="aaaa1111-aaaa-1111-aaaa-111111111111",
        run_b_id="bbbb2222-bbbb-2222-bbbb-222222222222",
    )
    assert diff["masked"] is True
    assert len(diff["tables"]) == 1
    bucket = diff["tables"][0]
    divergent_rows = {c["row_id"] for c in bucket["divergent_cells"]}
    a_only_rows = {c["row_id"] for c in bucket["a_only"]}
    b_only_rows = {c["row_id"] for c in bucket["b_only"]}
    assert divergent_rows == {"r1"}
    assert a_only_rows == {"r2"}
    assert b_only_rows == {"r3"}
    # Identical r4 cell did not surface.
    assert "r4" not in divergent_rows
    assert "r4" not in a_only_rows
    assert "r4" not in b_only_rows


def test_value_changes_diff_masks_unless_revealed() -> None:
    """Default mask hides values; reveal=True passes them through."""
    op = _seed_run_with_op(run_id="cccc3333-cccc-3333-cccc-333333333333")
    _seed_run_with_op(run_id="dddd4444-dddd-4444-dddd-444444444444")
    _add_value_change(
        run_id="cccc3333-cccc-3333-cccc-333333333333",
        op_id=op,
        table="main.silver.t",
        row_id="r1",
        column="amount",
        old_value="alice@example.com",
        new_value="ALICE@example.com",
    )
    _add_value_change(
        run_id="dddd4444-dddd-4444-dddd-444444444444",
        op_id=op,  # match op_id for identity
        table="main.silver.t",
        row_id="r1",
        column="amount",
        old_value="bob@example.com",
        new_value="BOB@example.com",
    )

    masked = run_diff.build_value_changes_diff(
        app.state.session_factory,
        run_a_id="cccc3333-cccc-3333-cccc-333333333333",
        run_b_id="dddd4444-dddd-4444-dddd-444444444444",
    )
    cell = masked["tables"][0]["divergent_cells"][0]
    assert cell["a_new_value"] == "***"
    assert cell["b_new_value"] == "***"

    revealed = run_diff.build_value_changes_diff(
        app.state.session_factory,
        run_a_id="cccc3333-cccc-3333-cccc-333333333333",
        run_b_id="dddd4444-dddd-4444-dddd-444444444444",
        reveal=True,
    )
    cell = revealed["tables"][0]["divergent_cells"][0]
    assert cell["a_new_value"] == "ALICE@example.com"
    assert cell["b_new_value"] == "BOB@example.com"


def test_value_changes_diff_top_k_truncates() -> None:
    """top_k=2 truncates a 5-cell divergent set + flags the bucket."""
    op_a = _seed_run_with_op(run_id="eeee5555-eeee-5555-eeee-555555555555")
    _seed_run_with_op(run_id="ffff6666-ffff-6666-ffff-666666666666")
    for i in range(5):
        _add_value_change(
            run_id="eeee5555-eeee-5555-eeee-555555555555",
            op_id=op_a,
            table="main.silver.t",
            row_id=f"r{i}",
            column="amount",
            old_value="0",
            new_value="1",
        )
        _add_value_change(
            run_id="ffff6666-ffff-6666-ffff-666666666666",
            op_id=op_a,
            table="main.silver.t",
            row_id=f"r{i}",
            column="amount",
            old_value="0",
            new_value="2",
        )

    diff = run_diff.build_value_changes_diff(
        app.state.session_factory,
        run_a_id="eeee5555-eeee-5555-eeee-555555555555",
        run_b_id="ffff6666-ffff-6666-ffff-666666666666",
        top_k=2,
    )
    bucket = diff["tables"][0]
    assert bucket["truncated"] is True
    assert len(bucket["divergent_cells"]) == 2


def test_column_lineage_diff_categorises_changes() -> None:
    """only-in-a / only-in-b / kind_changed / detail_changed all surface."""
    op_a = _seed_run_with_op(run_id="aaaa9999-aaaa-9999-aaaa-999999999999")
    _seed_run_with_op(run_id="bbbb9999-bbbb-9999-bbbb-999999999999")

    # Edge identical on both runs (must NOT appear).
    for run_id in (
        "aaaa9999-aaaa-9999-aaaa-999999999999",
        "bbbb9999-bbbb-9999-bbbb-999999999999",
    ):
        _add_column_edge(
            run_id=run_id,
            op_id=op_a,
            source_table="main.bronze.t",
            source_column="amount",
            target_table="main.silver.t",
            target_column="amount",
            transform_kind="identity",
        )
    # Edge with same identity but different transform_kind.
    _add_column_edge(
        run_id="aaaa9999-aaaa-9999-aaaa-999999999999",
        op_id=op_a,
        source_table="main.bronze.t",
        source_column="qty",
        target_table="main.silver.t",
        target_column="qty",
        transform_kind="identity",
    )
    _add_column_edge(
        run_id="bbbb9999-bbbb-9999-bbbb-999999999999",
        op_id=op_a,
        source_table="main.bronze.t",
        source_column="qty",
        target_table="main.silver.t",
        target_column="qty",
        transform_kind="derived",
    )
    # Edge only in A.
    _add_column_edge(
        run_id="aaaa9999-aaaa-9999-aaaa-999999999999",
        op_id=op_a,
        source_table="main.bronze.t",
        source_column="legacy_only_a",
        target_table="main.silver.t",
        target_column="legacy_only_a",
    )
    # Edge only in B.
    _add_column_edge(
        run_id="bbbb9999-bbbb-9999-bbbb-999999999999",
        op_id=op_a,
        source_table="main.bronze.t",
        source_column="new_in_b",
        target_table="main.silver.t",
        target_column="new_in_b",
    )

    diff = run_diff.build_column_lineage_diff(
        app.state.session_factory,
        run_a_id="aaaa9999-aaaa-9999-aaaa-999999999999",
        run_b_id="bbbb9999-bbbb-9999-bbbb-999999999999",
    )
    only_a_cols = {e["source_column"] for e in diff["edges_only_in_a"]}
    only_b_cols = {e["source_column"] for e in diff["edges_only_in_b"]}
    changed_cols = {c["a"]["source_column"] for c in diff["edges_changed"]}
    assert only_a_cols == {"legacy_only_a"}
    assert only_b_cols == {"new_in_b"}
    assert changed_cols == {"qty"}
    # Identical edge (amount) absent.
    for bucket in (diff["edges_only_in_a"], diff["edges_only_in_b"]):
        assert all(e["source_column"] != "amount" for e in bucket)
    for change in diff["edges_changed"]:
        assert change["a"]["source_column"] != "amount"
