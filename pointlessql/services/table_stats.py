"""Per-column profiling for UC tables.

Runs a single DuckDB pass over each column: ``count``, ``null_count``,
``distinct_count`` (via ``approx_count_distinct``), ``min``, ``max``,
``mean`` (numeric only), and a ``top_5`` histogram when
``distinct_count <= TOP_K_DISTINCT_CEILING``.  Results are cached
by ``(full_name, delta_log_version, column_name)`` in the
:class:`~pointlessql.models.TableStats` table so repeat profile
requests against an unchanged Delta version are a single index
seek.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from pointlessql.models import TableStats

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Columns with more than this many distinct values skip ``top_5``
# because the GROUP BY pass itself becomes the slow part.  Tests
# override the 10k default via the ``top_k_ceiling`` kwarg on
# :func:`compute_stats`.
TOP_K_DISTINCT_CEILING = 10_000

_NUMERIC_TYPES = {
    "INTEGER",
    "BIGINT",
    "SMALLINT",
    "TINYINT",
    "DOUBLE",
    "FLOAT",
    "REAL",
    "DECIMAL",
    "NUMERIC",
    "HUGEINT",
    "UINTEGER",
    "UBIGINT",
    "USMALLINT",
    "UTINYINT",
}


def read_delta_log_version(storage_location: str) -> int:
    """Return the current Delta log version for *storage_location*.

    Args:
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        The Delta ``version()`` integer.
    """
    import deltalake

    return int(deltalake.DeltaTable(storage_location).version())


def _is_numeric(column_type: str) -> bool:
    """Return whether *column_type* is a DuckDB numeric type.

    Args:
        column_type: DuckDB type string (possibly parametric).

    Returns:
        ``True`` when the base type is a known numeric.
    """
    head = (column_type or "").upper().split("(", 1)[0]
    return head in _NUMERIC_TYPES


def _stats_for_column(
    conn: Any,
    view: str,
    column_name: str,
    column_type: str,
    *,
    top_k_ceiling: int = TOP_K_DISTINCT_CEILING,
) -> dict[str, Any]:
    """Compute stats for a single column via two small DuckDB queries.

    Args:
        conn: Live DuckDB connection.
        view: Quoted view identifier registered via
            :func:`pointlessql.pql.engine.register_delta_view`.
        column_name: Column to profile.
        column_type: Column DuckDB type string.
        top_k_ceiling: Skip ``top_5`` when distinct_count exceeds this.

    Returns:
        Dict with ``count`` / ``null_count`` / ``distinct_count`` /
        ``min`` / ``max`` / ``mean`` (numeric only) / ``top_5``
        (when cardinality permits) keys.  All values are JSON-safe.
    """
    numeric = _is_numeric(column_type)
    # DuckDB allows double-quoting both the view identifier (the
    # 3-part UC name registered by register_delta_view) and the
    # column — identifiers containing dots otherwise bind as
    # schema.table lookups.
    quoted_view = f'"{view}"'
    quoted_col = f'"{column_name}"'
    # One-pass aggregate query.  ``mean`` is only selected when the
    # column is numeric to avoid type errors on strings / dates.
    mean_expr = f"avg({quoted_col})" if numeric else "NULL"
    sql = (
        f"SELECT count(*) AS row_count, "
        f"count(*) FILTER (WHERE {quoted_col} IS NULL) AS null_count, "
        f"approx_count_distinct({quoted_col}) AS distinct_count, "
        f"min({quoted_col})::VARCHAR AS min_value, "
        f"max({quoted_col})::VARCHAR AS max_value, "
        f"{mean_expr} AS mean_value "
        f"FROM {quoted_view}"
    )
    row = conn.execute(sql).fetchone()
    row_count = int(row[0]) if row[0] is not None else 0
    null_count = int(row[1]) if row[1] is not None else 0
    distinct_count = int(row[2]) if row[2] is not None else 0
    min_value = row[3]
    max_value = row[4]
    mean_value = float(row[5]) if numeric and row[5] is not None else None

    top_5: list[list[Any]] | None = None
    if 0 < distinct_count <= top_k_ceiling:
        top_sql = (
            f"SELECT {quoted_col}::VARCHAR AS v, count(*) AS c "
            f"FROM {quoted_view} "
            f"WHERE {quoted_col} IS NOT NULL "
            f"GROUP BY 1 ORDER BY c DESC LIMIT 5"
        )
        top_5 = [[r[0], int(r[1])] for r in conn.execute(top_sql).fetchall()]

    return {
        "column_name": column_name,
        "column_type": column_type,
        "count": row_count,
        "null_count": null_count,
        "distinct_count": distinct_count,
        "min": min_value,
        "max": max_value,
        "mean": mean_value,
        "top_5": top_5,
        "is_numeric": numeric,
    }


def compute_stats(
    full_name: str,
    storage_location: str,
    columns: list[dict[str, str]],
    *,
    top_k_ceiling: int = TOP_K_DISTINCT_CEILING,
    conn: Any = None,
) -> dict[str, dict[str, Any]]:
    """Profile every *columns* entry against the registered Delta view.

    Args:
        full_name: UC three-part name used as the view identifier.
        storage_location: Filesystem path / URI of the Delta table.
        columns: Iterable of ``{"name": str, "type": str}`` dicts.
        top_k_ceiling: Threshold above which ``top_5`` is skipped.
        conn: Optional pre-created DuckDB connection; a transient
            one is created and closed when ``None``.

    Returns:
        Mapping ``column_name → stats dict`` in the order *columns*
        was iterated.
    """
    import duckdb

    from pointlessql.pql.engine import register_delta_view

    should_close = False
    if conn is None:
        conn = duckdb.connect()
        should_close = True
    try:
        register_delta_view(conn, full_name, storage_location)
        result: dict[str, dict[str, Any]] = {}
        for column in columns:
            name = column["name"]
            type_text = column.get("type", "")
            try:
                result[name] = _stats_for_column(
                    conn,
                    full_name,
                    name,
                    type_text,
                    top_k_ceiling=top_k_ceiling,
                )
            except Exception as exc:  # noqa: BLE001 — per-column isolation
                logger.exception(
                    "table_stats: column %s.%s profile failed",
                    full_name,
                    name,
                )
                result[name] = {
                    "column_name": name,
                    "column_type": type_text,
                    "error": str(exc),
                }
        return result
    finally:
        if should_close:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — diagnostic
                logger.debug("table_stats: conn.close raised", exc_info=True)


def write_cached(
    factory: sessionmaker[Session],
    *,
    full_name: str,
    delta_log_version: int,
    stats: dict[str, dict[str, Any]],
) -> int:
    """Persist *stats* into :class:`~pointlessql.models.TableStats`.

    Existing rows for the same ``(full_name, delta_log_version,
    column_name)`` are overwritten so repeat profile calls converge
    instead of raising on the unique constraint.

    Args:
        factory: SQLAlchemy session factory.
        full_name: UC table name.
        delta_log_version: The log version profiled.
        stats: Mapping ``column_name → stats dict``.

    Returns:
        The number of rows written.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        # Drop any stale rows at exactly this (full_name, version)
        # so the write is idempotent without needing dialect-specific
        # ``ON CONFLICT`` / ``ON DUPLICATE KEY`` clauses.
        session.execute(
            delete(TableStats).where(
                TableStats.full_name == full_name,
                TableStats.delta_log_version == delta_log_version,
            )
        )
        rows = 0
        for column_name, stats_dict in stats.items():
            session.add(
                TableStats(
                    full_name=full_name,
                    delta_log_version=delta_log_version,
                    column_name=column_name,
                    stats_json=json.dumps(stats_dict, default=str),
                    computed_at=now,
                )
            )
            rows += 1
        session.commit()
        return rows


def read_cached(
    factory: sessionmaker[Session],
    *,
    full_name: str,
    delta_log_version: int | None = None,
) -> list[dict[str, Any]] | None:
    """Return cached stats for *full_name* at a version, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        full_name: UC table name.
        delta_log_version: Version to read.  When ``None`` the caller
            is not filtering by version — rows for every cached
            version come back in ``(delta_log_version, column_name)``
            order, which is typically not what the UI wants but is
            useful for the admin cache-clear flow.

    Returns:
        List of per-column dicts (``column_name``, ``stats``,
        ``delta_log_version``, ``computed_at``), or ``None`` when
        nothing is cached at that coordinate.
    """
    with factory() as session:
        stmt = select(TableStats).where(TableStats.full_name == full_name)
        if delta_log_version is not None:
            stmt = stmt.where(TableStats.delta_log_version == delta_log_version)
        stmt = stmt.order_by(TableStats.delta_log_version, TableStats.column_name)
        rows = list(session.scalars(stmt).all())
        if not rows:
            return None
        return [
            {
                "column_name": r.column_name,
                "delta_log_version": r.delta_log_version,
                "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                "stats": json.loads(r.stats_json),
            }
            for r in rows
        ]


def delete_cached(factory: sessionmaker[Session], full_name: str) -> int:
    """Drop every cached row for *full_name*.

    Args:
        factory: SQLAlchemy session factory.
        full_name: UC table name.

    Returns:
        Number of rows deleted.
    """
    with factory() as session:
        result = session.execute(delete(TableStats).where(TableStats.full_name == full_name))
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
