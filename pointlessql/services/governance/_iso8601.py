"""ISO-8601 timestamp enforcement (F5).

Walks a DataFrame's timestamp-like columns and checks every value
parses cleanly as ISO-8601.  Modes:

* ``off``      — no-op.
* ``warn``     — collect violations, return them; caller emits a
  warning audit row but does not block.
* ``strict``   — raise :class:`Iso8601Violation` on the first
  violation; caller surfaces as ``403`` via the central error map.

The validator is data-engine-agnostic: it accepts anything that walks
like a pandas DataFrame (has ``.columns`` and ``.iter_rows``-ish via
``.iloc``).
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from typing import Any

from pointlessql.exceptions import PermissionDeniedError

ISO8601_MODES: tuple[str, ...] = ("off", "warn", "strict")

_DATE_LIKE_DTYPES: tuple[str, ...] = (
    "datetime64",
    "datetime",
    "date",
    "timestamp",
)


_ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?"
    r"(?:Z|[+\-]\d{2}:?\d{2})?)?$"
)


@dataclasses.dataclass(frozen=True)
class Iso8601Finding:
    """One ISO-8601 violation encountered during validation."""

    column: str
    row_index: int
    value: str


class Iso8601Violation(PermissionDeniedError):
    """Strict-mode signal: a write contained non-ISO-8601 timestamps.

    Surfaces via the central error-handler as HTTP 403 with the
    findings list in ``detail``.
    """

    def __init__(self, findings: list[Iso8601Finding]) -> None:
        """Carry findings so the central error map can render them."""
        super().__init__("ISO-8601 violation in write payload")
        self.findings = findings

    def extension_members(self) -> dict[str, Any]:
        """Return JSON-serialisable detail for the FastAPI handler."""
        return {
            "violations": [
                {"column": f.column, "row": f.row_index, "value": f.value} for f in self.findings
            ],
        }


def _is_string_column(dtype_name: str) -> bool:
    return dtype_name.startswith("object") or dtype_name.startswith("string")


def _is_date_column(dtype_name: str) -> bool:
    return any(dtype_name.startswith(prefix) for prefix in _DATE_LIKE_DTYPES)


def _looks_like_timestamp_column(column: str) -> bool:
    """Heuristic: column name implies a timestamp surface."""
    lowered = column.lower()
    return any(token in lowered for token in ("_at", "_time", "_ts", "timestamp", "date", "_dt"))


def _value_is_iso8601(value: Any) -> bool:
    """Return ``True`` when *value* matches the ISO-8601 grammar."""
    if value is None:
        return True
    if isinstance(value, (datetime.datetime, datetime.date)):
        return True
    s = str(value).strip()
    if not s:
        return True
    return _ISO_DATE_RE.match(s) is not None


def validate_timestamps(
    df: Any,
    *,
    mode: str,
) -> list[Iso8601Finding]:
    """Validate every timestamp-like column in *df*.

    Args:
        df: DataFrame-like object with ``.columns`` + ``[col].iloc``.
        mode: One of :data:`ISO8601_MODES`.

    Returns:
        Findings list (empty when clean).  In ``strict`` mode, raises
        instead of returning when the list is non-empty.

    Raises:
        Iso8601Violation: In ``strict`` mode, on first column with
            violations.
        ValueError: When *mode* is not in :data:`ISO8601_MODES`.
    """
    if mode not in ISO8601_MODES:
        raise ValueError(f"unknown iso8601 mode: {mode!r}")
    if mode == "off":
        return []

    findings: list[Iso8601Finding] = []
    raw_columns = getattr(df, "columns", None)
    if raw_columns is None:
        return findings
    columns = list(raw_columns)
    for column in columns:
        series = df[column]
        dtype_name = str(getattr(series, "dtype", "")).lower()
        if _is_date_column(dtype_name):
            continue
        if not (_is_string_column(dtype_name) and _looks_like_timestamp_column(column)):
            continue
        for row_index, value in enumerate(series.tolist()):
            if not _value_is_iso8601(value):
                findings.append(
                    Iso8601Finding(
                        column=str(column),
                        row_index=row_index,
                        value=str(value)[:120],
                    )
                )
                if mode == "strict":
                    raise Iso8601Violation(findings)
    return findings
