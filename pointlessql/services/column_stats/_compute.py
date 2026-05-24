"""Read a Delta table and compute per-column stats.

The Phase-91 NL→SQL chat needs a quick "what's in this table" view
before drafting SQL: row count, per-column nullability and
cardinality, plus min/max for numeric columns and top-5 modes for
strings.  Computed via the existing :class:`PQL.table` adapter so
the engine choice (pandas / duckdb / polars) matches whatever the
rest of the editor uses.

Results are cached per ``(principal, table_fqn)`` for
``STATS_CACHE_TTL_SECONDS`` (default 5 minutes) so the LLM can poll
the endpoint multiple times during a chat turn without re-reading
the table.  Cache is process-local — no Redis dependency for what
is essentially a hint surface.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pointlessql.config import Settings
    from pointlessql.types import TableFqn

STATS_CACHE_TTL_SECONDS: int = 300
"""How long a successful stats computation is cached.

Five minutes is short enough that table edits during an active
chat session refresh on the next tool call, but long enough that a
typical multi-turn refinement doesn't pay the scan cost twice.
"""

_STATS_CACHE_MAX_ENTRIES: int = 128

_NUMERIC_DTYPE_PREFIXES: tuple[str, ...] = ("int", "float", "uint")

_cache: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_cache_lock: Lock = Lock()


def compute_table_stats(
    settings: Settings,
    principal: str,
    full_name: TableFqn,
) -> dict[str, Any]:
    """Return cached or freshly-computed stats for *full_name*.

    Args:
        settings: PointlesSQL settings — used to construct the
            principal-scoped soyuz client via
            :func:`make_principal_client`.
        principal: Caller's identity for catalog auth + cache
            keying.  Same string the dispatcher uses as
            ``X-Principal``.
        full_name: Fully-qualified ``catalog.schema.table`` reference.

    Returns:
        A JSON-friendly dict with two top-level keys:

        * ``row_count``: integer total row count from the scan.
        * ``columns``: list of per-column stat dicts, each carrying
          ``name`` / ``dtype`` / ``nullability_pct`` / ``n_distinct``
          plus the numeric or string add-on (``min`` + ``max`` for
          numerics, ``top_values`` for strings).
    """
    cache_key = (principal, str(full_name))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = _read_and_summarise(settings, principal, full_name)
    _cache_put(cache_key, payload)
    return payload


def invalidate_table_stats(full_name: TableFqn | None = None) -> None:
    """Drop cache entries — whole cache, or just one table.

    Args:
        full_name: When provided, only entries for this FQN across
            all principals are dropped.  ``None`` clears everything
            (used by tests).
    """
    with _cache_lock:
        if full_name is None:
            _cache.clear()
            return
        target = str(full_name)
        for key in [k for k in _cache if k[1] == target]:
            _cache.pop(key, None)


def _cache_get(key: tuple[str, str]) -> dict[str, Any] | None:
    """Return cached payload if fresh, else ``None``."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        stamped_at, payload = hit
        if now - stamped_at > STATS_CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        # Bump recency.
        _cache.move_to_end(key)
        return payload


def _cache_put(key: tuple[str, str], payload: dict[str, Any]) -> None:
    """Insert payload + evict oldest if over capacity."""
    with _cache_lock:
        _cache[key] = (time.monotonic(), payload)
        _cache.move_to_end(key)
        while len(_cache) > _STATS_CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def _read_and_summarise(
    settings: Settings,
    principal: str,
    full_name: TableFqn,
) -> dict[str, Any]:
    """Open the table via PQL + run the pandas reduction."""
    from pointlessql.pql import PQL
    from pointlessql.services.soyuz_client import (
        make_principal_client,
        make_soyuz_client,
    )

    client = (
        make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
    )
    pql = PQL(client=client, settings=settings)
    frame = pql.table(full_name)
    df = _materialise_pandas(frame)
    return _summarise_frame(df)


def _materialise_pandas(frame: Any) -> Any:
    """Coerce engine-specific frame to a pandas DataFrame."""
    if hasattr(frame, "df") and hasattr(frame, "limit"):
        # DuckDB relation — materialise the lazy plan.
        return frame.df()
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    return frame


def _summarise_frame(df: Any) -> dict[str, Any]:
    """Reduce a pandas DataFrame to the JSON-friendly stats dict."""
    row_count = int(len(df))
    columns: list[dict[str, Any]] = []
    for name in df.columns:
        series = df[name]
        dtype = str(series.dtype)
        nullability_pct = _nullability_pct(series, row_count)
        n_distinct = int(series.nunique(dropna=True))
        column_payload: dict[str, Any] = {
            "name": str(name),
            "dtype": dtype,
            "nullability_pct": nullability_pct,
            "n_distinct": n_distinct,
        }
        if _is_numeric_dtype(dtype):
            column_payload.update(_numeric_extremes(series))
        else:
            column_payload["top_values"] = _top_string_values(series)
        columns.append(column_payload)
    return {"row_count": row_count, "columns": columns}


def _nullability_pct(series: Any, row_count: int) -> float:
    """Percent of NULL values in *series*, rounded to 2 decimals."""
    if row_count == 0:
        return 0.0
    null_count = int(series.isna().sum())
    return round(100.0 * null_count / row_count, 2)


def _is_numeric_dtype(dtype: str) -> bool:
    """Heuristic for pandas numeric dtypes (int*, uint*, float*)."""
    lowered = dtype.lower()
    return any(lowered.startswith(p) for p in _NUMERIC_DTYPE_PREFIXES)


def _numeric_extremes(series: Any) -> dict[str, Any]:
    """Return min/max of a numeric series; both ``None`` if all-null."""
    if series.dropna().empty:
        return {"min": None, "max": None}
    return {"min": _scalar(series.min()), "max": _scalar(series.max())}


def _top_string_values(series: Any, k: int = 5) -> list[dict[str, Any]]:
    """Top-k value counts of a non-numeric series, ordered desc."""
    if series.dropna().empty:
        return []
    counts = series.value_counts(dropna=True).head(k)
    return [{"value": _scalar(value), "count": int(count)} for value, count in counts.items()]


def _scalar(value: Any) -> Any:
    """Coerce numpy/pandas scalars to plain Python for JSON-encoding."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError, TypeError:
            return str(value)
    return value
