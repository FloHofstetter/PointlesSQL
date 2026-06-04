"""Self-generated statistics: light shape capture + latest read-back.

Two responsibilities:

* :func:`light_shape` computes a cheap per-column null/distinct
  summary from the in-memory frame a write already holds, so the
  write path never re-scans the Delta table.  It is duck-typed across
  the engine frame types (pandas first; pyarrow / polars best-effort)
  and never raises — a frame it can't read yields an empty shape.
* :func:`read_latest_statistics` returns the most recent snapshot per
  table for a product, with the freshness lag computed at read time.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProductStatistics
from pointlessql.types import SessionFactory


def light_shape(df: Any) -> dict[str, Any]:
    """Return a cheap ``{column_count, columns:{...}}`` shape for *df*.

    Per column: ``null_count`` and ``distinct`` (the latter ``None``
    when the engine can't supply it cheaply).  Best-effort — any frame
    shape the helper doesn't recognise (or any error) yields an empty
    ``{}`` so the write path is never disrupted.

    Args:
        df: The in-memory frame being written (pandas / pyarrow /
            polars).

    Returns:
        Shape dict, or ``{}`` when the frame couldn't be summarised.
    """
    try:
        # pandas-like: isna()/nunique() + columns.
        if hasattr(df, "isna") and hasattr(df, "nunique") and hasattr(df, "columns"):
            nulls = df.isna().sum()
            distinct = df.nunique(dropna=True)
            columns: dict[str, Any] = {}
            for col in df.columns:
                columns[str(col)] = {
                    "null_count": int(nulls[col]),
                    "distinct": int(distinct[col]),
                }
            return {"column_count": len(columns), "columns": columns}

        # pyarrow Table: column_names + per-column null_count.  Distinct
        # is left ``None`` (a full ``unique`` scan isn't worth it on the
        # write path; pandas is the default engine anyway).
        if hasattr(df, "column_names") and hasattr(df, "column"):
            columns = {}
            for name in df.column_names:
                arr = df.column(name)
                columns[str(name)] = {
                    "null_count": int(arr.null_count),
                    "distinct": None,
                }
            return {"column_count": len(columns), "columns": columns}

        # polars DataFrame: null_count() returns a 1-row frame.
        if hasattr(df, "null_count") and hasattr(df, "n_unique") and hasattr(df, "columns"):
            null_row = df.null_count().to_dicts()[0]
            columns = {}
            for name in df.columns:
                try:
                    distinct_val = int(df[name].n_unique())
                except Exception:  # noqa: BLE001
                    # bare-broad-ok: distinct is best-effort, never blocks a write
                    distinct_val = None
                columns[str(name)] = {
                    "null_count": int(null_row.get(name, 0)),
                    "distinct": distinct_val,
                }
            return {"column_count": len(columns), "columns": columns}
    except Exception:  # noqa: BLE001
        # bare-broad-ok: shape capture must never break a write
        return {}
    return {}


def read_latest_statistics(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    table_name: str | None = None,
    now: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the latest statistics snapshot per table for a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product whose snapshots to read.
        table_name: When set, restrict to a single table.
        now: Reference instant for the freshness-lag computation;
            defaults to wall-clock UTC (pinned in tests).

    Returns:
        One dict per table — ``table_name``, ``delta_log_version``,
        ``row_count``, ``profile_kind``, ``freshness_lag_minutes``
        (computed here), ``computed_at`` (ISO), and the parsed
        ``shape``.  Ordered by ``table_name``.
    """
    reference = now or datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductStatistics)
                .where(DataProductStatistics.data_product_id == data_product_id)
                .order_by(
                    DataProductStatistics.table_name.asc(),
                    DataProductStatistics.created_at.desc(),
                )
            ).all()
        )

    seen: set[str] = set()
    latest: list[dict[str, Any]] = []
    for row in rows:
        if table_name is not None and row.table_name != table_name:
            continue
        if row.table_name in seen:
            continue
        seen.add(row.table_name)
        created = row.created_at
        lag_minutes: int | None = None
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.UTC)
            lag_minutes = max(0, int((reference - created).total_seconds() // 60))
        try:
            shape = json.loads(row.shape_json) if row.shape_json else {}
        except (TypeError, ValueError):
            shape = {}
        latest.append(
            {
                "table_name": row.table_name,
                "delta_log_version": row.delta_log_version,
                "row_count": row.row_count,
                "profile_kind": row.profile_kind,
                "freshness_lag_minutes": lag_minutes,
                "computed_at": row.created_at.isoformat() if row.created_at else None,
                "shape": shape,
            }
        )
    return latest
