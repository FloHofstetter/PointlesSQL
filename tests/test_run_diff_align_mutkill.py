"""Mutation-killing tests for run-diff pair alignment + per-slot diffs.

Covers the ordinal and content (greedy nearest-match) alignment
strategies for ops and tool calls, the per-slot field diffs, and the
one-layer params/args dict diff.  Lightweight attribute stand-ins are
used in place of ORM rows since the helpers only read columns.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.services.run_diff._align import (
    _content_align_ops,
    _content_align_tool_calls,
    _diff_op_pair,
    _diff_tool_call_pair,
    _ordinal_align_ops,
    _ordinal_align_tool_calls,
)
from pointlessql.services.run_diff._serialize import _params_diff


def _op(
    *,
    ordinal: int = 0,
    op_name: str = "merge",
    target_table: str = "c.s.t",
    rows_affected: int | None = 0,
    delta_version_after: int | None = None,
    error_message: str | None = None,
    params_json: str = "{}",
) -> Any:
    return SimpleNamespace(
        ordinal=ordinal,
        op_name=op_name,
        target_table=target_table,
        rows_affected=rows_affected,
        delta_version_before=None,
        delta_version_after=delta_version_after,
        started_at=None,
        finished_at=None,
        error_message=error_message,
        params_json=params_json,
    )


def _call(
    *,
    tool_name: str = "sql",
    args_json: str = "{}",
    result_summary: str | None = "",
) -> Any:
    return SimpleNamespace(
        tool_name=tool_name,
        args_json=args_json,
        result_summary=result_summary,
        duration_ms=0,
        called_at=None,
    )


# --- ordinal alignment ----------------------------------------------------


def test_ordinal_align_zips_equal_length() -> None:
    a = [_op(ordinal=0), _op(ordinal=1)]
    b = [_op(ordinal=0), _op(ordinal=1)]
    pairs = _ordinal_align_ops(a, b)
    assert [(x is a[i], y is b[i]) for i, (x, y) in enumerate(pairs)] == [
        (True, True),
        (True, True),
    ]


def test_ordinal_align_pads_shorter_a_side_with_none() -> None:
    a = [_op(ordinal=0)]
    b = [_op(ordinal=0), _op(ordinal=1)]
    pairs = _ordinal_align_ops(a, b)
    assert len(pairs) == 2
    assert pairs[1][0] is None and pairs[1][1] is b[1]


def test_ordinal_align_pads_shorter_b_side_with_none() -> None:
    a = [_op(ordinal=0), _op(ordinal=1)]
    b = [_op(ordinal=0)]
    pairs = _ordinal_align_ops(a, b)
    assert pairs[1][0] is a[1] and pairs[1][1] is None


def test_ordinal_align_empty_inputs() -> None:
    assert _ordinal_align_ops([], []) == []


def test_ordinal_align_tool_calls_pads() -> None:
    a = [_call()]
    b = [_call(), _call()]
    pairs = _ordinal_align_tool_calls(a, b)
    assert len(pairs) == 2 and pairs[1][0] is None and pairs[1][1] is b[1]


def test_ordinal_align_tool_calls_longer_a_pads_b_without_indexerror() -> None:
    # Guards the ``i < len(calls_b)`` bound (a ``<=`` mutant would
    # index past the end of the shorter B list).
    a = [_call(), _call()]
    b = [_call()]
    pairs = _ordinal_align_tool_calls(a, b)
    assert pairs[1][0] is a[1] and pairs[1][1] is None


# --- content alignment: ops -----------------------------------------------


def test_content_align_matches_on_name_and_table() -> None:
    a = [_op(op_name="merge", target_table="t1")]
    b = [_op(op_name="merge", target_table="t1")]
    pairs = _content_align_ops(a, b)
    assert pairs == [(a[0], b[0])]


def test_content_align_no_match_keeps_a_as_half_pair() -> None:
    a = [_op(op_name="merge", target_table="t1")]
    b = [_op(op_name="write_table", target_table="t1")]
    pairs = _content_align_ops(a, b)
    # A unmatched inline, then B unmatched at the end.
    assert pairs == [(a[0], None), (None, b[0])]


def test_content_align_picks_nearest_ordinal_candidate() -> None:
    a = [_op(op_name="merge", target_table="t", ordinal=5)]
    far = _op(op_name="merge", target_table="t", ordinal=1)
    near = _op(op_name="merge", target_table="t", ordinal=6)
    pairs = _content_align_ops(a, [far, near])
    # ordinal 6 is distance 1 from 5; ordinal 1 is distance 4.
    assert pairs[0] == (a[0], near)
    assert (None, far) in pairs


def test_content_align_b_used_once() -> None:
    a = [_op(op_name="merge", target_table="t"), _op(op_name="merge", target_table="t")]
    b = [_op(op_name="merge", target_table="t")]
    pairs = _content_align_ops(a, b)
    assert pairs[0] == (a[0], b[0])
    assert pairs[1] == (a[1], None)


def test_content_align_leftover_b_appended_last() -> None:
    a = [_op(op_name="merge", target_table="t")]
    b = [_op(op_name="merge", target_table="t"), _op(op_name="delete", target_table="t")]
    pairs = _content_align_ops(a, b)
    assert pairs[-1] == (None, b[1])


def test_content_align_unmatched_a_does_not_stop_later_matches() -> None:
    # First A op has no counterpart; it must `continue`, not `break`,
    # so the second A op can still match.
    a = [_op(op_name="delete", target_table="t"), _op(op_name="merge", target_table="t")]
    b = [_op(op_name="merge", target_table="t")]
    pairs = _content_align_ops(a, b)
    assert (a[1], b[0]) in pairs
    assert (a[0], None) in pairs


# --- content alignment: tool calls ----------------------------------------


def test_content_align_tool_calls_matches_name_nearest_index() -> None:
    a = [_call(tool_name="sql")]
    b = [_call(tool_name="other"), _call(tool_name="sql"), _call(tool_name="sql")]
    pairs = _content_align_tool_calls(a, b)
    # A index 0 -> nearest "sql" by index distance is b[1] (dist 1) not b[2].
    assert pairs[0] == (a[0], b[1])


def test_content_align_tool_calls_unmatched_a_then_b() -> None:
    a = [_call(tool_name="x")]
    b = [_call(tool_name="y")]
    pairs = _content_align_tool_calls(a, b)
    assert pairs == [(a[0], None), (None, b[0])]


# --- _diff_op_pair --------------------------------------------------------


def test_diff_op_pair_none_side_returns_payloads_only() -> None:
    diff = _diff_op_pair(None, _op())
    assert diff["a_op"] is None
    assert diff["b_op"] is not None
    assert "op_name_diff" not in diff


def test_diff_op_pair_reports_name_and_table() -> None:
    diff = _diff_op_pair(
        _op(op_name="merge", target_table="t1"),
        _op(op_name="delete", target_table="t2"),
    )
    assert diff["op_name_diff"] == {"a": "merge", "b": "delete"}
    assert diff["target_table_diff"] == {"a": "t1", "b": "t2"}


def test_diff_op_pair_rows_affected_delta_with_none_coalesced() -> None:
    diff = _diff_op_pair(_op(rows_affected=None), _op(rows_affected=10))
    assert diff["rows_affected_diff"] == 10


def test_diff_op_pair_exact_delta_with_zero_side() -> None:
    # b coalesces 0, not 1: delta is exactly -5.
    diff = _diff_op_pair(_op(rows_affected=5), _op(rows_affected=0))
    assert diff["rows_affected_diff"] == -5


def test_diff_op_pair_equal_rows_no_diff() -> None:
    diff = _diff_op_pair(_op(rows_affected=4), _op(rows_affected=4))
    assert "rows_affected_diff" not in diff


def test_diff_op_pair_both_zero_rows_no_diff() -> None:
    # 0 coalesces to 0 on both sides (an ``or 1`` mutant would fire).
    diff = _diff_op_pair(_op(rows_affected=0), _op(rows_affected=0))
    assert "rows_affected_diff" not in diff


def test_diff_op_pair_error_presence_change() -> None:
    diff = _diff_op_pair(_op(error_message=None), _op(error_message="boom"))
    assert diff["error_diff"] == {"a": None, "b": "boom"}


def test_diff_op_pair_error_cleared_on_b_side() -> None:
    # a-side error is read (not hard-coded None): a has error, b doesn't.
    diff = _diff_op_pair(_op(error_message="boom"), _op(error_message=None))
    assert diff["error_diff"] == {"a": "boom", "b": None}


def test_diff_op_pair_params_diff() -> None:
    diff = _diff_op_pair(_op(params_json='{"k": 1}'), _op(params_json='{"k": 2}'))
    assert diff["params_diff"]["changed"]["k"] == {"a": 1, "b": 2}


# --- _diff_tool_call_pair -------------------------------------------------


def test_diff_tool_call_pair_none_side_returns_payloads_only() -> None:
    # Either side None must short-circuit before tool_name access.
    diff = _diff_tool_call_pair(None, _call())
    assert diff["a_call"] is None and diff["b_call"] is not None
    assert "tool_name_diff" not in diff


def test_diff_tool_call_pair_dict_args_use_params_diff() -> None:
    diff = _diff_tool_call_pair(_call(args_json='{"q": "a"}'), _call(args_json='{"q": "b"}'))
    assert diff["args_diff"]["changed"]["q"] == {"a": "a", "b": "b"}


def test_diff_tool_call_pair_invalid_json_one_side_still_dict_diffs() -> None:
    # Unparseable args become {} (not None), so a dict-vs-dict diff
    # still runs against the valid side.
    diff = _diff_tool_call_pair(_call(args_json="not json"), _call(args_json='{"k": 1}'))
    assert diff["args_diff"] == {"added": ["k"]}


def test_diff_tool_call_pair_mixed_dict_and_list_uses_lengths() -> None:
    # One dict, one list -> not both dict -> length fallback (and no
    # crash from calling .items() on a list).
    diff = _diff_tool_call_pair(_call(args_json='{"k": 1}'), _call(args_json="[1, 2]"))
    assert diff["args_diff"] == {"a_len": 8, "b_len": 6}


def test_diff_tool_call_pair_non_dict_args_fall_back_to_lengths() -> None:
    diff = _diff_tool_call_pair(_call(args_json="[1]"), _call(args_json="[1, 2, 3]"))
    assert diff["args_diff"] == {"a_len": 3, "b_len": 9}


def test_diff_tool_call_pair_result_summary_reports_lengths_only() -> None:
    diff = _diff_tool_call_pair(_call(result_summary="hi"), _call(result_summary="hello"))
    assert diff["result_summary_diff"] == {"a_len": 2, "b_len": 5}


def test_diff_tool_call_pair_equal_result_summary_no_diff() -> None:
    # Equal summaries coalesce identically (an ``and ""`` mutant would
    # spuriously flag a diff).
    diff = _diff_tool_call_pair(_call(result_summary="same"), _call(result_summary="same"))
    assert "result_summary_diff" not in diff


def test_diff_tool_call_pair_name_change() -> None:
    diff = _diff_tool_call_pair(_call(tool_name="sql"), _call(tool_name="python"))
    assert diff["tool_name_diff"] == {"a": "sql", "b": "python"}


# --- _params_diff ---------------------------------------------------------


def test_params_diff_equal_is_empty() -> None:
    assert _params_diff({"a": 1}, {"a": 1}) == {}


def test_params_diff_added_removed_changed() -> None:
    out = _params_diff({"a": 1, "b": 2}, {"b": 9, "c": 3})
    assert out["added"] == ["c"]
    assert out["removed"] == ["a"]
    assert out["changed"] == {"b": {"a": 2, "b": 9}}
