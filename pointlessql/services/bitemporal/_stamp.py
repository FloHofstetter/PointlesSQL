"""Processing-time injection for the bitemporal write convention.

Data Mesh treats every record as carrying two clocks: *processing time*
(when the platform recorded it) and *event/business time* (when the fact
happened).  The platform can stamp processing time itself; this module
adds a standard processing-time column to a write frame just before it
lands.  Business/event time stays the producer's responsibility — the
platform can't infer it — so only processing time is injected here.

Duck-typed across the engine frame types (pandas first, then pyarrow);
best-effort so a frame it can't stamp passes through unchanged and a
write is never blocked.
"""

from __future__ import annotations

import datetime
from typing import Any


def inject_processing_time(
    df: Any,
    *,
    column: str,
    now: datetime.datetime | None = None,
) -> Any:
    """Return *df* with a standard processing-time column stamped.

    Args:
        df: The in-memory frame being written (pandas / pyarrow).
        column: The processing-time column name.
        now: The instant to stamp; defaults to ``datetime.now(UTC)``.

    Returns:
        A frame with *column* set to *now* on every row.  The original
        frame is returned unchanged when its type is unrecognised or
        stamping fails (best-effort — a write must never break on this).
    """
    timestamp = now or datetime.datetime.now(datetime.UTC)
    try:
        import pandas as pd

        if isinstance(df, pd.DataFrame):
            stamped = df.copy()
            stamped[column] = timestamp
            return stamped
    except ImportError:  # pragma: no cover — pandas is a hard dep
        pass
    except Exception:  # noqa: BLE001
        # bare-broad-ok: processing-time stamping must never break a write
        return df

    try:
        import pyarrow as pa

        if isinstance(df, pa.Table):
            n = df.num_rows
            arr = pa.array([timestamp] * n, type=pa.timestamp("us", tz="UTC"))
            if column in df.schema.names:
                return df.set_column(df.schema.get_field_index(column), column, arr)
            return df.append_column(column, arr)
    except ImportError:  # pragma: no cover — pyarrow is a hard dep
        pass
    except Exception:  # noqa: BLE001
        # bare-broad-ok: processing-time stamping must never break a write
        return df

    return df
