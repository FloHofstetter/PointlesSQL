# pyright: reportUnusedFunction=false
"""Per-row serializers + the one-layer params/args dict diff."""

from __future__ import annotations

import json
from typing import Any

from pointlessql.models import AgentRunOperation, AgentRunToolCall


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
