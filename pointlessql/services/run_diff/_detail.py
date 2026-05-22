# pyright: reportPrivateUsage=false
"""``build_detail_diff`` — the operations + tool-calls cap-bounded diff payload."""

from __future__ import annotations

from typing import Any, Literal

from pointlessql.models import AgentRunOperation, AgentRunToolCall
from pointlessql.services.run_diff._align import (
    _content_align_ops,
    _content_align_tool_calls,
    _diff_op_pair,
    _diff_tool_call_pair,
    _ordinal_align_ops,
    _ordinal_align_tool_calls,
)

AlignmentMode = Literal["ordinal", "content"]


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
