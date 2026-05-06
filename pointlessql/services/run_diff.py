"""Op-by-op + tool-call-by-tool-call diff service.

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
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, select

from pointlessql.models import (
    AgentRunOperation,
    AgentRunToolCall,
    LineageColumnMap,
    LineageRowReject,
    LineageValueChange,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

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


def _diff_op_pair(op_a: AgentRunOperation | None, op_b: AgentRunOperation | None) -> dict[str, Any]:
    """Per-slot diff between aligned operation rows."""
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
    """Per-slot diff between aligned tool-call rows."""
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


def _reject_buckets(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Return ``{reject_reason: count}`` for one run.

    Args:
        factory: SQLAlchemy session factory.
        run_id: ``AgentRun.id`` to bucket.

    Returns:
        Dict keyed by :class:`LineageRowReject.reason`.  Empty when
        the run has no rejects (``track_rejects=True`` not set on
        any merge).
    """
    with factory() as session:
        stmt = (
            select(LineageRowReject.reason, func.count(LineageRowReject.id))
            .where(LineageRowReject.run_id == run_id)
            .group_by(LineageRowReject.reason)
        )
        return {reason: int(count) for reason, count in session.execute(stmt).all()}


def _value_change_buckets(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Return ``{target_table: count}`` of value changes for one run."""
    with factory() as session:
        stmt = (
            select(LineageValueChange.target_table, func.count(LineageValueChange.id))
            .where(LineageValueChange.run_id == run_id)
            .group_by(LineageValueChange.target_table)
        )
        return {table: int(count) for table, count in session.execute(stmt).all()}


def _row_count_per_table(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Sum ``rows_affected`` per target table for one run."""
    with factory() as session:
        stmt = (
            select(
                AgentRunOperation.target_table,
                func.coalesce(func.sum(AgentRunOperation.rows_affected), 0),
            )
            .where(
                AgentRunOperation.agent_run_id == run_id,
                AgentRunOperation.target_table.is_not(None),
            )
            .group_by(AgentRunOperation.target_table)
        )
        return {
            table: int(total) for table, total in session.execute(stmt).all() if table is not None
        }


def build_lineage_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
) -> dict[str, Any]:
    """Compose the  lineage-shaped delta between two runs.

    The diff focuses on what *forensics* needs:

    * ``reject_pattern_shift`` — bucketed reject reasons on each
      side, plus a ``delta`` per reason (``b - a``) so a shift
      from "0 schema_mismatch" to "47 schema_mismatch" jumps out.
    * ``value_change_volume_per_table`` — per-target counts on
      each side; same delta structure.
    * ``row_count_delta_per_table`` — sum of ``rows_affected``
      per target.

    No soyuz roundtrip — every input is local.  Schema-drift
    (column-list compare) is intentionally deferred; it would
    require fan-out through ``UnityCatalogClient.get_table`` for
    every distinct table touched, which the current routes don't
    cache yet.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.

    Returns:
        ``{"reject_pattern_shift": {reasons, delta},
        "value_change_volume_per_table": {tables, delta},
        "row_count_delta_per_table": {tables, delta}}``.
    """
    rejects_a = _reject_buckets(factory, run_a_id)
    rejects_b = _reject_buckets(factory, run_b_id)
    vc_a = _value_change_buckets(factory, run_a_id)
    vc_b = _value_change_buckets(factory, run_b_id)
    rows_a = _row_count_per_table(factory, run_a_id)
    rows_b = _row_count_per_table(factory, run_b_id)
    return {
        "reject_pattern_shift": _shift_dict(rejects_a, rejects_b),
        "value_change_volume_per_table": _shift_dict(vc_a, vc_b),
        "row_count_delta_per_table": _shift_dict(rows_a, rows_b),
    }


_VALUE_CHANGES_DEFAULT_TOP_K = 50


def _load_value_changes(
    session: Session, run_id: str
) -> dict[tuple[str, int, str, str], LineageValueChange]:
    """Index :class:`LineageValueChange` rows by (table, op_id, row_id, column).

    The composite key uniquely identifies a single cell within a
    run.  When a run wrote the same cell more than once across
    multiple ops the *last* one wins — runs almost never do that
    in practice, and the cockpit's diff view doesn't try to
    visualise op-level cell history yet.
    """
    stmt = select(LineageValueChange).where(LineageValueChange.run_id == run_id)
    out: dict[tuple[str, int, str, str], LineageValueChange] = {}
    for row in session.scalars(stmt).all():
        key = (row.target_table, row.op_id, row.target_row_id, row.target_column)
        out[key] = row
    return out


def build_value_changes_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
    top_k: int = _VALUE_CHANGES_DEFAULT_TOP_K,
    reveal: bool = False,
) -> dict[str, Any]:
    """Cell-level diff of :class:`LineageValueChange` rows across two runs.

    Extends :func:`build_lineage_diff` (volumes only) with the
    actual diverging cells.  For every (target_table,
    op_id, row_id, column) cell present in *both* runs, compares
    ``new_value``: equal pairs drop, divergent pairs surface as a
    single row in ``divergent_cells`` of the corresponding table
    bucket.  Cells unique to one run also surface as
    ``a_only`` / ``b_only`` lists per table.

    Cell values are masked to ``"***"`` unless ``reveal=True``;
    the route layer only flips that when the caller is admin so
    auditor-scope Hermes flows never leak cleartext.

    Output is capped at ``top_k`` rows per (table, op_id, axis)
    triple.  When the cap fires the bucket carries
    ``truncated=True`` so the UI can link to the existing
    ``/audit/value-changes`` page for full detail.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.
        top_k: Per-bucket row cap (default 50).
        reveal: When ``True``, store cleartext values; otherwise
            mask all ``a_value`` / ``b_value`` cells.

    Returns:
        ``{"top_k": int, "tables": [{"target_table", "op_id",
        "divergent_cells": [...], "a_only": [...], "b_only": [...],
        "truncated": bool}, ...]}``.
    """
    with factory() as session:
        cells_a = _load_value_changes(session, run_a_id)
        cells_b = _load_value_changes(session, run_b_id)

    keys = set(cells_a.keys()) | set(cells_b.keys())
    by_bucket: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = {}

    def _mask(value: str | None) -> str | None:
        if value is None:
            return None
        return value if reveal else "***"

    for key in sorted(keys):
        target_table, op_id, row_id, column = key
        bucket = by_bucket.setdefault(
            (target_table, op_id),
            {"divergent_cells": [], "a_only": [], "b_only": []},
        )
        cell_a = cells_a.get(key)
        cell_b = cells_b.get(key)
        if cell_a is not None and cell_b is not None:
            if cell_a.new_value == cell_b.new_value:
                continue
            bucket["divergent_cells"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "a_old_value": _mask(cell_a.old_value),
                    "a_new_value": _mask(cell_a.new_value),
                    "b_old_value": _mask(cell_b.old_value),
                    "b_new_value": _mask(cell_b.new_value),
                }
            )
        elif cell_a is not None:
            bucket["a_only"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "old_value": _mask(cell_a.old_value),
                    "new_value": _mask(cell_a.new_value),
                }
            )
        else:
            assert cell_b is not None  # noqa: S101 — exhausted the OR above
            bucket["b_only"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "old_value": _mask(cell_b.old_value),
                    "new_value": _mask(cell_b.new_value),
                }
            )

    tables: list[dict[str, Any]] = []
    for (target_table, op_id), data in sorted(by_bucket.items()):
        truncated = False
        for axis in ("divergent_cells", "a_only", "b_only"):
            rows = data[axis]
            if len(rows) > top_k:
                truncated = True
                data[axis] = rows[:top_k]
        tables.append(
            {
                "target_table": target_table,
                "op_id": op_id,
                "divergent_cells": data["divergent_cells"],
                "a_only": data["a_only"],
                "b_only": data["b_only"],
                "truncated": truncated,
            }
        )

    return {"top_k": top_k, "masked": not reveal, "tables": tables}


_ColumnEdgeKey = tuple[int, str, str, str, str]


def _column_edge_key(row: LineageColumnMap) -> _ColumnEdgeKey:
    """Composite identity used to align two runs' column-lineage rows."""
    return (
        row.op_id,
        row.source_table or "",
        row.source_column or "",
        row.target_table,
        row.target_column,
    )


def build_column_lineage_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
) -> dict[str, Any]:
    """Edge-level diff of :class:`LineageColumnMap` rows across two runs.

    Identity tuple is ``(op_id, source_table, source_column,
    target_table, target_column)``.  Edges with the same identity
    but a different ``transform_kind`` or ``transform_detail`` are
    surfaced under ``edges_changed``.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.

    Returns:
        ``{"edges_only_in_a": [...], "edges_only_in_b": [...],
        "edges_changed": [{"a", "b", "kind_changed", "detail_changed"},
        ...]}``.  Each edge dict carries the five identity fields
        plus ``transform_kind`` / ``transform_detail``.
    """
    with factory() as session:
        rows_a = list(
            session.scalars(
                select(LineageColumnMap).where(LineageColumnMap.run_id == run_a_id)
            ).all()
        )
        rows_b = list(
            session.scalars(
                select(LineageColumnMap).where(LineageColumnMap.run_id == run_b_id)
            ).all()
        )

    by_key_a: dict[_ColumnEdgeKey, LineageColumnMap] = {_column_edge_key(r): r for r in rows_a}
    by_key_b: dict[_ColumnEdgeKey, LineageColumnMap] = {_column_edge_key(r): r for r in rows_b}
    keys_a = set(by_key_a.keys())
    keys_b = set(by_key_b.keys())

    def _serialize(row: LineageColumnMap) -> dict[str, Any]:
        return {
            "op_id": row.op_id,
            "source_table": row.source_table,
            "source_column": row.source_column,
            "target_table": row.target_table,
            "target_column": row.target_column,
            "transform_kind": row.transform_kind,
            "transform_detail": row.transform_detail,
        }

    edges_only_in_a = [_serialize(by_key_a[k]) for k in sorted(keys_a - keys_b)]
    edges_only_in_b = [_serialize(by_key_b[k]) for k in sorted(keys_b - keys_a)]
    edges_changed: list[dict[str, Any]] = []
    for key in sorted(keys_a & keys_b):
        a = by_key_a[key]
        b = by_key_b[key]
        kind_changed = a.transform_kind != b.transform_kind
        detail_changed = a.transform_detail != b.transform_detail
        if not kind_changed and not detail_changed:
            continue
        edges_changed.append(
            {
                "a": _serialize(a),
                "b": _serialize(b),
                "kind_changed": kind_changed,
                "detail_changed": detail_changed,
            }
        )

    return {
        "edges_only_in_a": edges_only_in_a,
        "edges_only_in_b": edges_only_in_b,
        "edges_changed": edges_changed,
    }


def _shift_dict(a: dict[str, int], b: dict[str, int]) -> dict[str, Any]:
    """Render ``{a: …, b: …, delta: …}`` over a union of keys.

    Args:
        a: Counts keyed by some bucket on the left side.
        b: Counts keyed by the same bucket on the right side.

    Returns:
        ``{"a": a_dict, "b": b_dict, "delta": {key: b - a}}``;
        keys missing on one side count as 0 there.  Sorted
        deterministically so the JSON response is reproducible.
    """
    keys = sorted(set(a.keys()) | set(b.keys()))
    delta = {k: int(b.get(k, 0)) - int(a.get(k, 0)) for k in keys}
    return {
        "a": {k: int(a.get(k, 0)) for k in keys},
        "b": {k: int(b.get(k, 0)) for k in keys},
        "delta": delta,
    }
