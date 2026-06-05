"""Pure decision and formatting logic for the ``alert_check`` executor.

The executor itself is a tangle of DB reads, UC privilege checks, threaded
DuckDB query execution, and webhook fan-out.  The I/O-free decisions it
makes along the way live here so they can be unit-tested without any of
that machinery: config validation, table-reference parsing, the
storage-location guard, the data-health summary string, and the
webhook-destination filter.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.models import AlertDestination


def validate_alert_config(config: dict[str, Any]) -> int:
    """Pull the ``alert_id`` out of an ``alert_check`` job config.

    Args:
        config: The executor's job-config dict.

    Returns:
        The validated ``alert_id``.

    Raises:
        ValidationError: When ``alert_id`` is absent or not an integer.
    """
    alert_id = config.get("alert_id")
    if not isinstance(alert_id, int):
        raise ValidationError("alert_check job config missing integer 'alert_id'")
    return alert_id


def parse_table_ref(full_name: str) -> tuple[str, str, str] | None:
    """Split a fully-qualified table name into ``(catalog, schema, table)``.

    Args:
        full_name: A dotted table reference from the prepared SQL.

    Returns:
        The three name parts, or ``None`` when ``full_name`` is not
        exactly three-part (the caller logs and aborts the check).
    """
    parts = full_name.split(".")
    if len(parts) != 3:
        return None
    return (parts[0], parts[1], parts[2])


def valid_storage_location(value: Any) -> str | None:
    """Return a usable storage location, or ``None`` when it is unset.

    Args:
        value: The ``storage_location`` field from UC table metadata.

    Returns:
        The location when it is a non-empty string, otherwise ``None``.
    """
    if isinstance(value, str) and value:
        return value
    return None


def build_alert_summary_md(
    alert_slug: str,
    row_count: int,
    condition_op: str,
    threshold: int,
) -> str:
    """Render the data-health card summary for a firing alert.

    Args:
        alert_slug: The firing alert's slug.
        row_count: Rows the alert query returned.
        condition_op: The condition operator (e.g. ``gt``).
        threshold: The compared threshold.

    Returns:
        A one-line Markdown summary for the feed card.
    """
    return f"Alert '{alert_slug}' fired — {row_count} rows {condition_op} {threshold}"


def active_webhook_destinations(
    dests: Iterable[AlertDestination],
) -> list[tuple[AlertDestination, str]]:
    """Keep only the destinations the webhook fan-out can deliver to.

    Pairs each surviving destination with its (now narrowed, non-empty)
    URL so the caller can dispatch without re-checking.

    Args:
        dests: Candidate destinations (already filtered to active rows
            by the caller's query).

    Returns:
        A ``(destination, url)`` pair for every destination whose
        ``kind`` is ``"webhook"`` and that carries a non-empty
        ``webhook_url``.
    """
    out: list[tuple[AlertDestination, str]] = []
    for d in dests:
        if d.kind == "webhook" and d.webhook_url:
            out.append((d, d.webhook_url))
    return out
