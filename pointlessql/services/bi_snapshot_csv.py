"""CSV serialisation of a BI-dashboard snapshot.

The AI/BI 2026 refresh ships tabular CSV attachments on dashboard
subscriptions.  A snapshot already freezes every widget's result
(columns + rows) into its payload; this module turns that frozen,
data-backed payload into one CSV document — a section per widget — so it
can be downloaded or attached to a scheduled delivery.

Pure string assembly over the snapshot payload; markdown and errored
widgets (which carry no tabular result) are skipped.
"""

from __future__ import annotations

import csv
import io
from typing import Any, cast


def _col_name(col: Any) -> str:
    """Return a column's display name, tolerating dict or string shapes."""
    if isinstance(col, dict):
        column = cast("dict[str, Any]", col)
        return str(column.get("name") or column.get("column") or "")
    return str(col)


def snapshot_to_csv(payload: dict[str, Any]) -> str:
    """Serialise a snapshot payload's data-backed widgets to CSV.

    Args:
        payload: The snapshot's ``{"title", "widgets": [...]}`` document.

    Returns:
        A CSV string with one ``# <title>`` section per data-backed
        widget (header row + data rows), blank-line separated.  An empty
        string when the payload carries no tabular widget.
    """
    widgets = payload.get("widgets")
    if not isinstance(widgets, list):
        return ""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    first = True
    for entry in cast("list[Any]", widgets):
        if not isinstance(entry, dict):
            continue
        widget = cast("dict[str, Any]", entry)
        columns = widget.get("columns")
        rows = widget.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            continue
        if not first:
            writer.writerow([])
        first = False
        title = widget.get("title") or f"widget {widget.get('widget_id')}"
        writer.writerow([f"# {title}"])
        writer.writerow([_col_name(col) for col in cast("list[Any]", columns)])
        for row in cast("list[Any]", rows):
            cells: list[Any] = cast("list[Any]", row) if isinstance(row, list) else [row]
            writer.writerow(["" if value is None else value for value in cells])
    return buffer.getvalue()
