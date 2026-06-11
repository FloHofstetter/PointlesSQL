"""Summarise DuckDB JSON runtime profiles for the editor UI.

DuckDB's ``enable_profiling='json'`` output is a recursive operator
tree whose key names have drifted across engine releases
(``operator_type`` vs ``name``, ``operator_timing`` vs ``timing``).
This module flattens that tree into a stable, render-ready summary:
one row per operator with wall-clock time, cardinality, and the
operator's share of the total measured time.  Everything is
best-effort — a profile the walker cannot interpret yields an empty
summary, never an exception, because the profile is diagnostics
attached to an already-successful query.
"""

from __future__ import annotations

from typing import Any

# Hard cap on summary rows; a pathological plan with thousands of
# operators would otherwise bloat the response payload and the
# query-history row it is persisted to.
MAX_OPERATORS = 50


def _node_name(node: dict[str, Any]) -> str:
    """Return the best available operator label for *node*."""
    for key in ("operator_type", "operator_name", "name"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "(unknown)"


def _node_time_seconds(node: dict[str, Any]) -> float:
    """Return the operator's measured wall-clock seconds, or 0.0."""
    for key in ("operator_timing", "timing", "cpu_time"):
        value = node.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return 0.0


def _node_rows(node: dict[str, Any]) -> int | None:
    """Return the operator's produced-row count when present."""
    for key in ("operator_cardinality", "cardinality", "rows_returned"):
        value = node.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return None


def _walk(node: Any, out: list[dict[str, Any]], depth: int) -> None:
    """Depth-first flatten of the profile tree into *out*."""
    if not isinstance(node, dict):
        return
    name = _node_name(node)
    # the synthetic root of newer profiles repeats the query text and
    # carries no operator semantics — skip it but keep walking.
    if name != "(unknown)" or depth > 0:
        out.append(
            {
                "operator": name,
                "depth": depth,
                "time_ms": round(_node_time_seconds(node) * 1000.0, 3),
                "rows": _node_rows(node),
                "extra": _extra_info(node),
            }
        )
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            _walk(child, out, depth + 1)


def _extra_info(node: dict[str, Any]) -> str | None:
    """Return a short human-readable detail string for *node*."""
    extra = node.get("extra_info")
    if isinstance(extra, str) and extra.strip():
        return extra.strip()[:200]
    if isinstance(extra, dict):
        parts = [f"{k}={v}" for k, v in list(extra.items())[:4] if isinstance(v, (str, int, float))]
        if parts:
            return ", ".join(parts)[:200]
    return None


def summarize_profile(tree: Any) -> dict[str, Any]:
    """Flatten a DuckDB JSON profile *tree* into a render-ready summary.

    Args:
        tree: The parsed profile JSON (``SQLResult.profile``).  Any
            shape is tolerated; non-dict input yields an empty summary.

    Returns:
        A dict with ``operators`` (flat list, slowest first, capped at
        :data:`MAX_OPERATORS`, each carrying ``operator`` / ``depth`` /
        ``time_ms`` / ``rows`` / ``pct`` / ``extra``),
        ``total_time_ms`` (the root latency when reported, otherwise
        the sum of operator timings), ``rows_returned`` (root-level
        when reported), and ``operator_count`` (pre-cap count).
    """
    flat: list[dict[str, Any]] = []
    _walk(tree, flat, 0)

    summed_ms = sum(op["time_ms"] for op in flat)
    total_ms = summed_ms
    rows_returned: int | None = None
    if isinstance(tree, dict):
        latency = tree.get("latency")
        if isinstance(latency, (int, float)) and latency > 0:
            total_ms = round(float(latency) * 1000.0, 3)
        root_rows = tree.get("rows_returned")
        if isinstance(root_rows, (int, float)) and root_rows >= 0:
            rows_returned = int(root_rows)

    denominator = summed_ms if summed_ms > 0 else None
    for op in flat:
        op["pct"] = round(op["time_ms"] / denominator * 100.0, 1) if denominator else 0.0

    operator_count = len(flat)
    flat.sort(key=lambda op: op["time_ms"], reverse=True)
    return {
        "operators": flat[:MAX_OPERATORS],
        "total_time_ms": round(total_ms, 3),
        "rows_returned": rows_returned,
        "operator_count": operator_count,
    }
