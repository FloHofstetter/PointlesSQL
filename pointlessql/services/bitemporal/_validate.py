"""Event-time column validation (F5 enforcement).

Called from the write path *after* :func:`inject_processing_time`.
Either silently passes (when the effective policy does not require it)
or raises :class:`BitemporalRequirementError` so a route can return a
4xx (or the agent driving the write can surface the failure).
"""

from __future__ import annotations

from typing import Any


class BitemporalRequirementError(ValueError):
    """Raised when a write violates the effective bitemporal policy."""


def _has_temporal_dtype(series: Any) -> bool:
    """Best-effort: True when *series* looks like a datetime-typed column."""
    dtype_str = str(getattr(series, "dtype", "")).lower()
    return "datetime" in dtype_str or "timestamp" in dtype_str or "date" in dtype_str


def validate_event_time_column(
    df: Any,
    *,
    column: str,
    require: bool,
) -> None:
    """Validate event-time column presence + dtype on a write frame.

    Args:
        df: The in-memory write frame (pandas / pyarrow).  When the
            type is unrecognised the function silently passes — the
            engine layer will fail loudly downstream.
        column: Expected event-time column name.
        require: When False the validation is skipped entirely.

    Raises:
        BitemporalRequirementError: When *require* is True and either
            the column is absent or carries a non-temporal dtype.
    """
    if not require:
        return
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        pd = None  # type: ignore[assignment]
    if pd is not None and isinstance(df, pd.DataFrame):
        if column not in df.columns:
            raise BitemporalRequirementError(
                f"event-time column {column!r} missing from write frame"
            )
        if not _has_temporal_dtype(df[column]):
            raise BitemporalRequirementError(
                f"event-time column {column!r} must carry a datetime dtype (got {df[column].dtype})"
            )
        return
    try:
        import pyarrow as pa
    except ImportError:  # pragma: no cover
        pa = None  # type: ignore[assignment]
    if pa is not None and isinstance(df, pa.Table):
        if column not in df.schema.names:
            raise BitemporalRequirementError(
                f"event-time column {column!r} missing from write frame"
            )
        ftype = df.schema.field(column).type
        if not (pa.types.is_timestamp(ftype) or pa.types.is_date(ftype)):
            raise BitemporalRequirementError(
                f"event-time column {column!r} must carry a timestamp/date dtype (got {ftype})"
            )
        return
    # Unknown frame type — nothing to validate.  Engine will fail
    # downstream if the column is truly missing.
    return
