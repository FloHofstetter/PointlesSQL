# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Pair-alignment helpers — ordinal and content strategies for ops + tool calls."""

from __future__ import annotations

import json
from typing import Any

from pointlessql.models import AgentRunOperation, AgentRunToolCall
from pointlessql.services.run_diff._serialize import (
    _params_diff,
    _serialize_op,
    _serialize_tool_call,
)


def _diff_op_pair(op_a: AgentRunOperation | None, op_b: AgentRunOperation | None) -> dict[str, Any]:
    """Per-slot diff between aligned operation rows.

    Compares ``op_name``, ``target_table``, ``rows_affected``,
    ``delta_version_after`` and the parsed ``params`` blob;
    side-effect-only fields like ``started_at`` carry no signal
    for "did this run produce the same data?" and are skipped.
    A ``None`` slot on either side returns the existing op
    payload unchanged so the UI can render it as an "extra slot"
    badge without inferring missing data.
    """
    a_dict = _serialize_op(op_a) if op_a is not None else None
    b_dict = _serialize_op(op_b) if op_b is not None else None
    diff: dict[str, Any] = {"a_op": a_dict, "b_op": b_dict}
    if a_dict is None or b_dict is None:
        return diff
    if a_dict["op_name"] != b_dict["op_name"]:
        diff["op_name_diff"] = {"a": a_dict["op_name"], "b": b_dict["op_name"]}
    if a_dict["target_table"] != b_dict["target_table"]:
        diff["target_table_diff"] = {"a": a_dict["target_table"], "b": b_dict["target_table"]}
    if (a_dict["rows_affected"] or 0) != (b_dict["rows_affected"] or 0):
        diff["rows_affected_diff"] = (b_dict["rows_affected"] or 0) - (a_dict["rows_affected"] or 0)
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
    """Per-slot diff between aligned tool-call rows.

    ``args_diff`` falls back to a length comparison when either
    side's ``args_json`` does not parse as a dict — non-dict
    payloads have no canonical key/value structure so a deeper
    diff would be misleading.  ``result_summary_diff`` reports
    only lengths, never the full string, so the diff route stays
    safe for auditor-scope viewers.
    """
    a_dict = _serialize_tool_call(call_a) if call_a is not None else None
    b_dict = _serialize_tool_call(call_b) if call_b is not None else None
    diff: dict[str, Any] = {"a_call": a_dict, "b_call": b_dict}
    if a_dict is None or b_dict is None:
        return diff
    if a_dict["tool_name"] != b_dict["tool_name"]:
        diff["tool_name_diff"] = {"a": a_dict["tool_name"], "b": b_dict["tool_name"]}
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
            diff["args_diff"] = {
                "a_len": len(a_dict["args_json"]),
                "b_len": len(b_dict["args_json"]),
            }
    if (a_dict["result_summary"] or "") != (b_dict["result_summary"] or ""):
        diff["result_summary_diff"] = {
            "a_len": len(a_dict["result_summary"] or ""),
            "b_len": len(b_dict["result_summary"] or ""),
        }
    return diff


def _ordinal_align_ops(
    ops_a: list[AgentRunOperation], ops_b: list[AgentRunOperation]
) -> list[tuple[AgentRunOperation | None, AgentRunOperation | None]]:
    """Zip ops_a and ops_b by index; pad the shorter side with ``None``.

    The right strategy when the two runs are deterministic replays
    of the same notebook — ordinal N on both sides should be the
    same op.  When the order can drift (e.g. parallel runs of an
    agent), :func:`_content_align_ops` is the better default; the
    caller picks via the ``align`` parameter on
    :func:`build_detail_diff`.
    """
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
        idx, match = min(candidates, key=lambda pair: abs(pair[1].ordinal - op_a.ordinal))
        used_b.add(idx)
        pairs.append((op_a, match))
    for i, op_b in enumerate(ops_b):
        if i not in used_b:
            pairs.append((None, op_b))
    return pairs


def _ordinal_align_tool_calls(
    calls_a: list[AgentRunToolCall], calls_b: list[AgentRunToolCall]
) -> list[tuple[AgentRunToolCall | None, AgentRunToolCall | None]]:
    """Zip tool-call lists by index; pad the shorter side with ``None``.

    Mirror of :func:`_ordinal_align_ops` for tool-call rows.
    Appropriate when the agents are deterministic replays of the
    same prompt; for divergent runs prefer
    :func:`_content_align_tool_calls`.
    """
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
    """Greedy ``tool_name`` match on call-order distance.

    Pairs each A-side call with the closest unused B-side call of
    the same ``tool_name``, where "closest" is the absolute
    difference in list index.  Calls without a partner land as
    half-pairs at the end (A's leftovers first, then B's) so the
    UI can render them as "extra calls on one side".
    """
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
