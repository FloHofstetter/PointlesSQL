"""Op-by-op + tool-call-by-tool-call diff service (Sprint 13.11.4b).

Pure-Python helpers that align two runs' ``agent_run_operations``
and ``agent_run_tool_calls`` row sets, then emit a per-slot diff
shaped for the Hermes ``pql_diff_runs(detail=True)`` tool.

Two alignment strategies, exposed through the ``align`` parameter:

* ``"ordinal"`` — pair op[i] from A with op[i] from B.  Fast,
  deterministic, but sensitive to insertions (one extra op in A
  shifts every later slot).
* ``"content"`` — greedy match on
  ``(op_name, target_table)`` (or ``tool_name`` for tool calls)
  with the smallest ordinal distance breaking ties.  More robust
  for "same notebook, different inputs" comparisons.

Diff fields are deliberately minimal — agents reading the diff
need actionable signal, not exhaustive byte-by-byte comparison.
``params_diff`` walks one JSON layer (added / removed / changed
keys); deeper structures are summarised by length.

The route caps the combined slot count at 500 to keep an LLM
transcript bounded; consumers can paginate if they really need
more.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pointlessql.models import AgentRunOperation, AgentRunToolCall

AlignmentMode = Literal["ordinal", "content"]


def _serialize_op(op: AgentRunOperation) -> dict[str, Any]:
    """Render an ``AgentRunOperation`` row to a JSON-safe dict."""
    try:
        params = json.loads(op.params_json)
    except json.JSONDecodeError:
        params = {}
    return {
        "ordinal": op.ordinal,
        "op_name": op.op_name,
        "target_table": op.target_table,
        "rows_affected": op.rows_affected,
        "delta_version_before": op.delta_version_before,
        "delta_version_after": op.delta_version_after,
        "started_at": op.started_at.isoformat() if op.started_at else None,
        "finished_at": op.finished_at.isoformat() if op.finished_at else None,
        "error_message": op.error_message,
        "params": params,
    }


def _serialize_tool_call(call: AgentRunToolCall) -> dict[str, Any]:
    """Render an ``AgentRunToolCall`` row to a JSON-safe dict."""
    return {
        "tool_name": call.tool_name,
        "args_json": call.args_json,
        "result_summary": call.result_summary,
        "duration_ms": call.duration_ms,
        "called_at": call.called_at.isoformat() if call.called_at else None,
    }


def _params_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """One-layer dict diff returning ``{added, removed, changed}``.

    Args:
        a: Left side dict.
        b: Right side dict.

    Returns:
        Empty when the dicts are equal.  Otherwise carries the
        keys present only in ``b`` (``added``), only in ``a``
        (``removed``), and the union of keys whose values differ
        (``changed`` mapping ``key → {a, b}``).
    """
    if a == b:
        return {}
    out: dict[str, Any] = {}
    a_keys = set(a.keys())
    b_keys = set(b.keys())
    added = sorted(b_keys - a_keys)
    removed = sorted(a_keys - b_keys)
    changed: dict[str, Any] = {}
    for key in a_keys & b_keys:
        if a[key] != b[key]:
            changed[key] = {"a": a[key], "b": b[key]}
    if added:
        out["added"] = added
    if removed:
        out["removed"] = removed
    if changed:
        out["changed"] = changed
    return out


def _diff_op_pair(
    op_a: AgentRunOperation | None, op_b: AgentRunOperation | None
) -> dict[str, Any]:
    """Per-slot diff between aligned operation rows."""
    a_dict = _serialize_op(op_a) if op_a is not None else None
    b_dict = _serialize_op(op_b) if op_b is not None else None
    diff: dict[str, Any] = {"a_op": a_dict, "b_op": b_dict}
    if a_dict is None or b_dict is None:
        return diff
    if a_dict["op_name"] != b_dict["op_name"]:
        diff["op_name_diff"] = {"a": a_dict["op_name"], "b": b_dict["op_name"]}
    if a_dict["target_table"] != b_dict["target_table"]:
        diff["target_table_diff"] = {
            "a": a_dict["target_table"], "b": b_dict["target_table"]
        }
    if (a_dict["rows_affected"] or 0) != (b_dict["rows_affected"] or 0):
        diff["rows_affected_diff"] = (
            (b_dict["rows_affected"] or 0) - (a_dict["rows_affected"] or 0)
        )
    if a_dict["delta_version_after"] != b_dict["delta_version_after"]:
        diff["delta_version_after_diff"] = {
            "a": a_dict["delta_version_after"],
            "b": b_dict["delta_version_after"],
        }
    if bool(a_dict["error_message"]) != bool(b_dict["error_message"]):
        diff["error_diff"] = {
            "a": a_dict["error_message"],
            "b": b_dict["error_message"],
        }
    p_diff = _params_diff(a_dict["params"], b_dict["params"])
    if p_diff:
        diff["params_diff"] = p_diff
    return diff


def _diff_tool_call_pair(
    call_a: AgentRunToolCall | None, call_b: AgentRunToolCall | None
) -> dict[str, Any]:
    """Per-slot diff between aligned tool-call rows."""
    a_dict = _serialize_tool_call(call_a) if call_a is not None else None
    b_dict = _serialize_tool_call(call_b) if call_b is not None else None
    diff: dict[str, Any] = {"a_call": a_dict, "b_call": b_dict}
    if a_dict is None or b_dict is None:
        return diff
    if a_dict["tool_name"] != b_dict["tool_name"]:
        diff["tool_name_diff"] = {
            "a": a_dict["tool_name"], "b": b_dict["tool_name"]
        }
    if a_dict["args_json"] != b_dict["args_json"]:
        try:
            a_args = json.loads(a_dict["args_json"])
        except json.JSONDecodeError:
            a_args = {}
        try:
            b_args = json.loads(b_dict["args_json"])
        except json.JSONDecodeError:
            b_args = {}
        if isinstance(a_args, dict) and isinstance(b_args, dict):
            a_typed: dict[str, Any] = {
                str(k): v  # type: ignore[reportUnknownArgumentType]
                for k, v in a_args.items()  # type: ignore[reportUnknownVariableType]
            }
            b_typed: dict[str, Any] = {
                str(k): v  # type: ignore[reportUnknownArgumentType]
                for k, v in b_args.items()  # type: ignore[reportUnknownVariableType]
            }
            arg_diff = _params_diff(a_typed, b_typed)
            if arg_diff:
                diff["args_diff"] = arg_diff
        else:
            diff["args_diff"] = {"a_len": len(a_dict["args_json"]),
                                 "b_len": len(b_dict["args_json"])}
    if (a_dict["result_summary"] or "") != (b_dict["result_summary"] or ""):
        diff["result_summary_diff"] = {
            "a_len": len(a_dict["result_summary"] or ""),
            "b_len": len(b_dict["result_summary"] or ""),
        }
    return diff


def _ordinal_align_ops(
    ops_a: list[AgentRunOperation], ops_b: list[AgentRunOperation]
) -> list[tuple[AgentRunOperation | None, AgentRunOperation | None]]:
    """Zip ops_a and ops_b by index; pad the shorter side with ``None``."""
    n = max(len(ops_a), len(ops_b))
    pairs: list[tuple[AgentRunOperation | None, AgentRunOperation | None]] = []
    for i in range(n):
        a = ops_a[i] if i < len(ops_a) else None
        b = ops_b[i] if i < len(ops_b) else None
        pairs.append((a, b))
    return pairs


def _content_align_ops(
    ops_a: list[AgentRunOperation], ops_b: list[AgentRunOperation]
) -> list[tuple[AgentRunOperation | None, AgentRunOperation | None]]:
    """Greedy ``(op_name, target_table)`` match on minimum ordinal distance.

    Ops in either list with no compatible counterpart land as a
    half-pair (one side ``None``) at the end of the result, A's
    leftovers first then B's.

    Args:
        ops_a: Left-side operations in ordinal order.
        ops_b: Right-side operations in ordinal order.

    Returns:
        List of pairs, matched first then unmatched from each side.
    """
    used_b: set[int] = set()
    pairs: list[tuple[AgentRunOperation | None, AgentRunOperation | None]] = []
    for op_a in ops_a:
        candidates = [
            (i, op_b)
            for i, op_b in enumerate(ops_b)
            if i not in used_b
            and op_b.op_name == op_a.op_name
            and op_b.target_table == op_a.target_table
        ]
        if not candidates:
            pairs.append((op_a, None))
            continue
        idx, match = min(
            candidates, key=lambda pair: abs(pair[1].ordinal - op_a.ordinal)
        )
        used_b.add(idx)
        pairs.append((op_a, match))
    for i, op_b in enumerate(ops_b):
        if i not in used_b:
            pairs.append((None, op_b))
    return pairs


def _ordinal_align_tool_calls(
    calls_a: list[AgentRunToolCall], calls_b: list[AgentRunToolCall]
) -> list[tuple[AgentRunToolCall | None, AgentRunToolCall | None]]:
    """Zip tool-call lists by index; pad the shorter side with ``None``."""
    n = max(len(calls_a), len(calls_b))
    pairs: list[tuple[AgentRunToolCall | None, AgentRunToolCall | None]] = []
    for i in range(n):
        a = calls_a[i] if i < len(calls_a) else None
        b = calls_b[i] if i < len(calls_b) else None
        pairs.append((a, b))
    return pairs


def _content_align_tool_calls(
    calls_a: list[AgentRunToolCall], calls_b: list[AgentRunToolCall]
) -> list[tuple[AgentRunToolCall | None, AgentRunToolCall | None]]:
    """Greedy ``tool_name`` match on call-order distance."""
    used_b: set[int] = set()
    pairs: list[tuple[AgentRunToolCall | None, AgentRunToolCall | None]] = []
    for i_a, call_a in enumerate(calls_a):
        candidates = [
            (i, call_b)
            for i, call_b in enumerate(calls_b)
            if i not in used_b and call_b.tool_name == call_a.tool_name
        ]
        if not candidates:
            pairs.append((call_a, None))
            continue
        idx, match = min(candidates, key=lambda pair: abs(pair[0] - i_a))
        used_b.add(idx)
        pairs.append((call_a, match))
    for i, call_b in enumerate(calls_b):
        if i not in used_b:
            pairs.append((None, call_b))
    return pairs


_DEFAULT_DIFF_CAP = 500


def build_detail_diff(
    *,
    ops_a: list[AgentRunOperation],
    ops_b: list[AgentRunOperation],
    tool_calls_a: list[AgentRunToolCall],
    tool_calls_b: list[AgentRunToolCall],
    align: AlignmentMode = "ordinal",
    cap: int = _DEFAULT_DIFF_CAP,
) -> dict[str, Any]:
    """Build the ``operations_diff`` + ``tool_calls_diff`` payload.

    Args:
        ops_a: Left-side operations in ordinal order.
        ops_b: Right-side operations in ordinal order.
        tool_calls_a: Left-side tool calls in ``called_at`` order.
        tool_calls_b: Right-side tool calls in ``called_at`` order.
        align: Strategy.  ``"ordinal"`` zips by index;
            ``"content"`` matches on ``(op_name, target_table)`` /
            ``tool_name`` with minimum ordinal distance.
        cap: Hard cap on the combined slot count (default 500).
            Slots beyond the cap are dropped + reflected in
            ``truncated``.

    Returns:
        ``{align, operations_diff, tool_calls_diff, truncated}``.
        ``truncated`` is a dict ``{operations: bool,
        tool_calls: bool}`` so the caller knows which side was
        clipped.
    """
    if align == "content":
        op_pairs = _content_align_ops(ops_a, ops_b)
        call_pairs = _content_align_tool_calls(tool_calls_a, tool_calls_b)
    else:
        op_pairs = _ordinal_align_ops(ops_a, ops_b)
        call_pairs = _ordinal_align_tool_calls(tool_calls_a, tool_calls_b)
    op_truncated = len(op_pairs) > cap
    call_truncated = len(call_pairs) > cap
    if op_truncated:
        op_pairs = op_pairs[:cap]
    if call_truncated:
        call_pairs = call_pairs[:cap]
    return {
        "align": align,
        "operations_diff": [_diff_op_pair(a, b) for a, b in op_pairs],
        "tool_calls_diff": [_diff_tool_call_pair(a, b) for a, b in call_pairs],
        "truncated": {
            "operations": op_truncated,
            "tool_calls": call_truncated,
        },
    }
