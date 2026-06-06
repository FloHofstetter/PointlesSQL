"""Categorise an edge by the dominant data type of its rowset.

The DP-Canvas editor colours each connection by data-type family so
that a glance at the canvas reveals where the numeric backbone runs,
where the text columns flow, and where temporal joins fan out.  The
categorisation is purely cosmetic — it does not feed back into the
compiler.  When the upstream schema is unknown (raw SQL blocks, empty
columns, unresolved errors) the edge falls back to the ``mixed``
bucket so the renderer never throws.
"""

from __future__ import annotations

import re

from pointlessql.services.canvas_df._types import ColumnSpec, PinSchema

EdgeCategory = str

_NUMERIC_RE = re.compile(
    r"^(?:U?(?:BIG|HUGE|TINY|SMALL)?INT(?:EGER)?|"
    r"DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL)",
    re.IGNORECASE,
)
_TEXT_RE = re.compile(r"^(?:VARCHAR|TEXT|CHAR|STRING|BLOB|BIT|UUID)", re.IGNORECASE)
_TEMPORAL_RE = re.compile(r"^(?:DATE|TIMESTAMP|TIME|INTERVAL)", re.IGNORECASE)
_BOOLEAN_RE = re.compile(r"^BOOL", re.IGNORECASE)
_COMPLEX_RE = re.compile(r"^(?:STRUCT|LIST|MAP|UNION|ARRAY|JSON)", re.IGNORECASE)


def _bucket(duckdb_type: str) -> EdgeCategory:
    t = (duckdb_type or "").strip()
    if not t:
        return "mixed"
    if _NUMERIC_RE.match(t):
        return "numeric"
    if _TEXT_RE.match(t):
        return "text"
    if _TEMPORAL_RE.match(t):
        return "temporal"
    if _BOOLEAN_RE.match(t):
        return "boolean"
    if _COMPLEX_RE.match(t):
        return "complex"
    return "mixed"


def categorize_columns(columns: list[ColumnSpec]) -> EdgeCategory:
    """Return the dominant bucket for *columns*.

    Empty input, all-unknown types, or a tie across multiple buckets
    falls back to ``"mixed"`` so the renderer can default to a neutral
    grey stroke instead of asserting a category.
    """
    if not columns:
        return "mixed"
    counts: dict[EdgeCategory, int] = {}
    for col in columns:
        bucket = _bucket(col.duckdb_type)
        counts[bucket] = counts.get(bucket, 0) + 1
    counts.pop("mixed", None)
    if not counts:
        return "mixed"
    top_count = max(counts.values())
    leaders = [b for b, c in counts.items() if c == top_count]
    if len(leaders) > 1:
        return "mixed"
    return leaders[0]


def categorize_pin_schema(schema: PinSchema | None) -> EdgeCategory:
    """Bucket *schema* by its dominant column-type family."""
    if schema is None or schema.unknown:
        return "mixed"
    return categorize_columns(list(schema.columns))


__all__ = ["categorize_columns", "categorize_pin_schema", "EdgeCategory"]
