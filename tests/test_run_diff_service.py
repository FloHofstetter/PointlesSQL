"""Pure-unit tests for the Sprint 13.11.4b run-diff service."""

from __future__ import annotations

import datetime as dt

from pointlessql.models import AgentRunOperation, AgentRunToolCall
from pointlessql.services.run_diff import build_detail_diff


def _op(
    *,
    ordinal: int,
    op_name: str,
    target: str | None,
    rows_affected: int = 0,
    delta_after: int | None = None,
    error: str | None = None,
    params: dict[str, object] | None = None,
) -> AgentRunOperation:
    """Construct an unpersisted ``AgentRunOperation`` for tests."""
    import json as _json

    started = dt.datetime(2026, 4, 25, 12, 0, 0, tzinfo=dt.UTC)
    return AgentRunOperation(
        id=ordinal,  # cosmetic; we never read the PK
        agent_run_id="run",
        ordinal=ordinal,
        op_name=op_name,
        params_json=_json.dumps(params or {}),
        target_table=target,
        input_sha=None,
        rows_affected=rows_affected,
        delta_version_before=None,
        delta_version_after=delta_after,
        started_at=started,
        finished_at=started,
        error_message=error,
    )


def _call(
    *,
    tool_name: str,
    args_json: str = "{}",
    result_summary: str | None = None,
) -> AgentRunToolCall:
    """Construct an unpersisted ``AgentRunToolCall`` for tests."""
    return AgentRunToolCall(
        agent_run_id="run",
        tool_name=tool_name,
        args_json=args_json,
        result_summary=result_summary,
        duration_ms=None,
        called_at=dt.datetime(2026, 4, 25, 12, 0, 0, tzinfo=dt.UTC),
    )


def test_ordinal_alignment_zips_with_padding() -> None:
    ops_a = [
        _op(ordinal=1, op_name="autoload", target="main.bronze.orders_raw"),
        _op(ordinal=2, op_name="merge", target="main.silver.orders"),
    ]
    ops_b = [
        _op(ordinal=1, op_name="autoload", target="main.bronze.orders_raw"),
        _op(ordinal=2, op_name="merge", target="main.silver.orders"),
        _op(ordinal=3, op_name="write_table", target="main.gold.orders_summary"),
    ]
    diff = build_detail_diff(
        ops_a=ops_a, ops_b=ops_b, tool_calls_a=[], tool_calls_b=[]
    )
    assert diff["align"] == "ordinal"
    assert len(diff["operations_diff"]) == 3
    # The third slot is unpaired on the A side.
    last = diff["operations_diff"][2]
    assert last["a_op"] is None
    assert last["b_op"]["op_name"] == "write_table"


def test_content_alignment_robust_to_insertion() -> None:
    """A run with one extra op early shouldn't shift every later slot."""
    ops_a = [
        _op(ordinal=1, op_name="autoload", target="main.bronze.t"),
        _op(ordinal=2, op_name="merge", target="main.silver.t"),
    ]
    ops_b = [
        _op(ordinal=1, op_name="autoload", target="main.bronze.t"),
        _op(
            ordinal=2,
            op_name="write_table",
            target="main.bronze.different",
            rows_affected=10,
        ),
        _op(ordinal=3, op_name="merge", target="main.silver.t"),
    ]
    diff = build_detail_diff(
        ops_a=ops_a,
        ops_b=ops_b,
        tool_calls_a=[],
        tool_calls_b=[],
        align="content",
    )
    matched = [
        slot for slot in diff["operations_diff"]
        if slot["a_op"] is not None and slot["b_op"] is not None
    ]
    assert len(matched) == 2
    # Ensure the merge ops align even though B inserted a write_table.
    matched_names = [slot["a_op"]["op_name"] for slot in matched]
    assert sorted(matched_names) == ["autoload", "merge"]


def test_per_op_diff_emits_relevant_fields_only() -> None:
    ops_a = [
        _op(
            ordinal=1,
            op_name="merge",
            target="main.silver.orders",
            rows_affected=10,
            delta_after=3,
            params={"strategy": "upsert", "on": ["id"]},
        )
    ]
    ops_b = [
        _op(
            ordinal=1,
            op_name="merge",
            target="main.silver.orders",
            rows_affected=20,
            delta_after=4,
            params={"strategy": "scd2", "on": ["id"], "cutover": "2026-01-01"},
        )
    ]
    diff = build_detail_diff(
        ops_a=ops_a, ops_b=ops_b, tool_calls_a=[], tool_calls_b=[]
    )
    pair = diff["operations_diff"][0]
    assert "op_name_diff" not in pair  # same name
    assert "target_table_diff" not in pair  # same target
    assert pair["rows_affected_diff"] == 10
    assert pair["delta_version_after_diff"] == {"a": 3, "b": 4}
    p = pair["params_diff"]
    assert p["added"] == ["cutover"]
    assert p["changed"]["strategy"] == {"a": "upsert", "b": "scd2"}


def test_tool_call_args_json_diff_walks_top_level_keys() -> None:
    calls_a = [_call(tool_name="pql_query", args_json='{"sql": "SELECT 1"}')]
    calls_b = [
        _call(
            tool_name="pql_query",
            args_json='{"sql": "SELECT 1", "max_rows": 50}',
        )
    ]
    diff = build_detail_diff(
        ops_a=[], ops_b=[], tool_calls_a=calls_a, tool_calls_b=calls_b
    )
    pair = diff["tool_calls_diff"][0]
    assert pair["args_diff"]["added"] == ["max_rows"]


def test_truncation_flag_set_when_cap_exceeded() -> None:
    ops_a = [
        _op(ordinal=i, op_name="write_table", target=f"t.s.t{i}")
        for i in range(1, 5)
    ]
    ops_b = [
        _op(ordinal=i, op_name="write_table", target=f"t.s.t{i}")
        for i in range(1, 5)
    ]
    diff = build_detail_diff(
        ops_a=ops_a, ops_b=ops_b, tool_calls_a=[], tool_calls_b=[], cap=2
    )
    assert diff["truncated"]["operations"] is True
    assert len(diff["operations_diff"]) == 2
    assert diff["truncated"]["tool_calls"] is False
