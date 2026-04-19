"""Condition evaluation + CloudEvents envelope construction."""

from __future__ import annotations

import datetime
from typing import Any

from pointlessql.exceptions import ValidationError


def evaluate_condition(row_count: int, op: str, threshold: int) -> bool:
    """Return whether *row_count* satisfies *op* against *threshold*.

    Args:
        row_count: Observed row count.
        op: One of ``gt`` / ``lt`` / ``eq`` / ``ne``.
        threshold: Compared value.

    Returns:
        ``True`` when the condition is met.

    Raises:
        ValidationError: On unknown operator.
    """
    if op == "gt":
        return row_count > threshold
    if op == "lt":
        return row_count < threshold
    if op == "eq":
        return row_count == threshold
    if op == "ne":
        return row_count != threshold
    raise ValidationError(f"Unknown condition_op {op!r}.")


def build_cloudevent(
    *,
    event_id: str,
    alert_slug: str,
    saved_query_slug: str,
    condition_op: str,
    threshold: int,
    row_count: int,
    duration_ms: int,
    referenced_tables: list[str],
    fired_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for a fired alert.

    Args:
        event_id: Unique event id (uuid4 hex).
        alert_slug: The firing alert's slug.
        saved_query_slug: The saved-query slug the alert watches.
        condition_op: The condition operator that fired.
        threshold: The threshold the condition was compared against.
        row_count: The observed row count.
        duration_ms: DuckDB wall-clock time for the query.
        referenced_tables: UC tables touched by the query.
        fired_at: UTC timestamp the check fired.

    Returns:
        A dict ready to ``json.dumps``-serialise onto the wire with
        ``Content-Type: application/cloudevents+json``.
    """
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": f"/pointlessql/alerts/{alert_slug}",
        "type": "sql.pointlessql.alert.fired.v1",
        "time": fired_at.astimezone(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": saved_query_slug,
        "data": {
            "alert_slug": alert_slug,
            "saved_query_slug": saved_query_slug,
            "condition": {"op": condition_op, "threshold": threshold},
            "row_count": row_count,
            "duration_ms": duration_ms,
            "referenced_tables": list(referenced_tables),
            "fired_at": fired_at.astimezone(datetime.UTC).isoformat(),
        },
    }
