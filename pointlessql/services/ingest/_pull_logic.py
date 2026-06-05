"""Pure decision and SQL-shaping logic for the ingest pull path.

Every branch the pull orchestrator makes that does *not* touch DuckDB
or the PQL write plane lives here: mapping-shape validation, the
incremental high-water SQL, the new-watermark computation, the
SELECT-shape choice, the write-strategy decision, and result coercion.

Keeping this logic I/O-free lets :func:`pointlessql.services.ingest.pull.pull_mapping`
stay a thin shell around the DuckDB read and the Delta write, and lets
each decision be unit-tested in isolation without a connection or a PQL
instance.
"""

from __future__ import annotations

from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.models.ingest import INGEST_PULL_MODES
from pointlessql.services.ingest.connectors import (
    ReaderSpec,
    quote_sql_identifier,
    quote_sql_string,
)


def coerce_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Validate the shape of a table-mapping dict.

    Args:
        mapping: One entry from ``IngestSource.table_mappings``.

    Returns:
        A normalised dict with the keys the pull path needs.

    Raises:
        ValidationError: When required keys are missing or have the
            wrong type.
    """
    source_table = str(mapping.get("source_table") or "").strip()
    target_fqn = str(mapping.get("target_fqn") or "").strip()
    mode = str(mapping.get("mode") or "full").strip()
    if mode not in INGEST_PULL_MODES:
        raise ValidationError(f"Mapping mode must be one of {INGEST_PULL_MODES}, got {mode!r}.")
    if not target_fqn or target_fqn.count(".") != 2:
        raise ValidationError(f"target_fqn must be 'catalog.schema.table', got {target_fqn!r}.")
    if mode == "incremental":
        hw_col = mapping.get("high_water_col")
        if not hw_col:
            raise ValidationError("incremental mode requires 'high_water_col' on the mapping.")
    return {
        "source_table": source_table,
        "target_fqn": target_fqn,
        "mode": mode,
        "high_water_col": mapping.get("high_water_col"),
        "last_high_water_value": mapping.get("last_high_water_value"),
    }


def wrap_with_high_water(spec: ReaderSpec, high_water_col: str, last_value: str | None) -> str:
    """Return SQL that selects only rows whose ``high_water_col`` is new.

    ``last_value`` is ``None`` on the very first incremental pull —
    we treat that as "everything qualifies" so the initial pull is a
    full ingest and subsequent pulls are deltas.

    Args:
        spec: The base reader spec.
        high_water_col: Source-side column to compare against.
        last_value: Previously-stored high-water value (string-encoded
            for JSON portability).

    Returns:
        A SQL string that wraps the base SELECT with the WHERE clause.
    """
    base_sql = spec.sql.rstrip(";").strip()
    col_q = quote_sql_identifier(high_water_col)
    if last_value is None:
        # Initial incremental pull = full snapshot.  Subsequent pulls
        # will filter.
        return f"SELECT * FROM ({base_sql}) AS _pql_src"
    return (
        f"SELECT * FROM ({base_sql}) AS _pql_src "
        f"WHERE {col_q} > {quote_sql_string(str(last_value))}"
    )


def max_high_water_sql(spec: ReaderSpec, high_water_col: str, last_value: str | None) -> str:
    """Build the SQL string that returns ``MAX(high_water_col)`` over the same window."""
    base_sql = spec.sql.rstrip(";").strip()
    col_q = quote_sql_identifier(high_water_col)
    where = ""
    if last_value is not None:
        where = f" WHERE {col_q} > {quote_sql_string(str(last_value))}"
    return f"SELECT MAX({col_q}) FROM ({base_sql}) AS _pql_src{where}"


def compute_new_high_water(row: tuple[Any, ...] | None, last_value: str | None) -> str | None:
    """Turn a ``MAX(high_water_col)`` result row into the value to persist.

    The MAX query runs against the post-cutoff window, so an empty
    window yields a ``NULL`` cell (``row[0] is None``).  In that case we
    keep the previous watermark rather than regressing it to ``None``;
    a non-null cell becomes the new string-encoded watermark.

    Args:
        row: The single-cell result of the MAX query, or ``None`` when
            the cursor returned no row at all.
        last_value: The watermark currently stored on the mapping.

    Returns:
        The watermark to persist: the fetched value (stringified) when
        the window was non-empty, otherwise the unchanged ``last_value``.
    """
    new_value = row[0] if row else None
    if new_value is not None:
        return str(new_value)
    # Empty incremental window — keep the previous value.
    return last_value


def prepare_select_sql(
    spec: ReaderSpec,
    mode: str,
    high_water_col: str | None,
    last_value: str | None,
) -> str:
    """Choose the SELECT that materialises the rows for this pull.

    Full refreshes read the base spec SQL verbatim (trailing semicolon
    stripped).  Incremental pulls wrap it with the high-water filter via
    :func:`wrap_with_high_water`.

    Args:
        spec: The base reader spec.
        mode: ``"full"`` or ``"incremental"``.
        high_water_col: The watermark column; required (non-``None``)
            when ``mode`` is ``"incremental"``.
        last_value: Previously-stored watermark, or ``None`` on the
            first incremental pull.

    Returns:
        The SQL string to execute for the row read.
    """
    if mode == "incremental":
        assert isinstance(high_water_col, str)
        return wrap_with_high_water(spec, high_water_col, last_value)
    return spec.sql.rstrip(";")


def select_write_strategy(
    mode: str,
    last_value: str | None,
    high_water_col: str | None,
) -> tuple[str, dict[str, Any]]:
    """Decide which PQL write call materialises the frame, and its kwargs.

    Full refreshes always overwrite.  An incremental pull overwrites on
    the first run (no watermark yet bootstraps the table) and upserts via
    merge thereafter — merge cannot create a missing table, so the first
    incremental pull is a full write.

    Args:
        mode: ``"full"`` or ``"incremental"``.
        last_value: Previously-stored watermark, or ``None`` on the
            first incremental pull.
        high_water_col: The merge key; used only on the merge path.

    Returns:
        A ``(operation, kwargs)`` pair where ``operation`` is
        ``"write_table"`` or ``"merge"`` and ``kwargs`` carries the
        arguments to splat into ``pql_instance.<operation>(df, fqn, ...)``.
    """
    if mode == "full" or last_value is None:
        return ("write_table", {"mode": "overwrite"})
    return ("merge", {"on": [high_water_col], "strategy": "upsert"})


def safe_row_count(df: Any) -> int:
    """Return a DataFrame's row count, defaulting to ``0`` on an odd shape.

    Args:
        df: The pandas frame returned by ``cursor.fetch_df()``.

    Returns:
        The number of rows, or ``0`` when ``df`` has no usable
        ``shape`` attribute.
    """
    return int(getattr(df, "shape", (0, 0))[0])
