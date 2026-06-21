"""Shared query-filter parsers for the admin gateway consoles.

The agent-gateway, AI-gateway, and governance-hub admin surfaces all
accept the same ``since`` (ISO-8601) and ``budget`` (decimal) query
filters and parse them identically — tolerating blank or malformed
input by falling back to ``None``.  The parsers live here so the three
consoles interpret a given ``?since=`` / ``?budget=`` the same way and a
change to that behaviour lands once.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation


def parse_since(value: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 ``since`` filter, tolerating bad input.

    Args:
        value: Raw query value.

    Returns:
        A timezone-aware datetime, or ``None`` when blank or
        unparseable.  A naive timestamp is assumed to be UTC.
    """
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


def parse_budget(value: str | None) -> Decimal | None:
    """Parse a numeric ``budget`` filter, tolerating bad input.

    Args:
        value: Raw query value.

    Returns:
        A :class:`Decimal`, or ``None`` when blank or non-numeric.
    """
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None
