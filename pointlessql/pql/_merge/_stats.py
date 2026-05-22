# pyright: reportUnusedFunction=false
"""Audit-side stats massagers: rows-affected + JSON-safe stats dict."""

from __future__ import annotations

from typing import Any


def _merge_rows_affected(stats: dict[str, Any]) -> int | None:
    """Best-effort total row count from the deltalake merge stats.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        Sum of inserted + updated for upsert; appended + closed for
        SCD-2; ``None`` when the keys cannot be located.
    """
    try:
        if stats.get("strategy") == "upsert":
            inserted = int(stats.get("num_target_rows_inserted", 0) or 0)
            updated = int(stats.get("num_target_rows_updated", 0) or 0)
            return inserted + updated
        if stats.get("strategy") == "scd2":
            appended = int(stats.get("rows_appended", 0) or 0)
            closed = 0
            close_stats = stats.get("close_stats") or {}
            if isinstance(close_stats, dict):
                closed = int(close_stats.get("num_target_rows_updated", 0) or 0)
            return appended + closed
    except (TypeError, ValueError):
        return None
    return None


def _stats_for_audit(stats: dict[str, Any]) -> dict[str, Any]:
    """Strip non-JSON-serialisable bits from the merge stats payload.

    Args:
        stats: Return value from :func:`_do_upsert` or :func:`_do_scd2`.

    Returns:
        A dict whose values are JSON-encodable (numbers, strings,
        nested dicts, lists).  Anything else gets stringified.
    """
    out: dict[str, Any] = {}
    for key, value in stats.items():
        if isinstance(value, (int, float, str, bool, type(None))):
            out[key] = value
        elif isinstance(value, dict):
            out[key] = _stats_for_audit(value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            out[key] = [
                v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
                for v in value  # pyright: ignore[reportUnknownVariableType]
            ]
        else:
            out[key] = str(value)
    return out
