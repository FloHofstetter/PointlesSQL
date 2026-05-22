# pyright: reportUnusedFunction=false
"""Per-strategy execution: ``_do_upsert``, ``_do_scd2``, ``_augment_for_scd2``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import deltalake
import pyarrow as pa

from pointlessql.pql._merge._constants import (
    SCD2_IS_CURRENT,
    SCD2_VALID_FROM,
    SCD2_VALID_TO,
)
from pointlessql.pql._types import ArrowTable


def _do_upsert(target_location: str, arrow_source: ArrowTable, on: list[str]) -> dict[str, Any]:
    """Run an upsert MERGE against the Delta table at *target_location*.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "upsert", **deltalake_merge_stats}``.
    """
    dt = deltalake.DeltaTable(target_location)
    predicate = " AND ".join(f"target.{col} = source.{col}" for col in on)
    # deltalake.merge typing wants its own ArrowArrayExportable union;
    # cast to Any at the boundary — runtime is still pyarrow.Table.
    stats = (
        dt.merge(
            source=cast(Any, arrow_source),
            predicate=predicate,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )
    return {"strategy": "upsert", **stats}


def _do_scd2(target_location: str, arrow_source: ArrowTable, on: list[str]) -> dict[str, Any]:
    """Run an SCD-2 close-and-append against the Delta table.

    Two-phase: the merge step closes any currently-open target row
    that matches the source key (``_valid_to = now``,
    ``_is_current = false``).  An append step then writes every
    source row as a new current version with ``_valid_from = now``,
    ``_valid_to = null``, ``_is_current = true``.  See the module
    docstring for the no-change-detection caveat.

    Args:
        target_location: Delta table URI.
        arrow_source: Source rows as a PyArrow Table.
        on: Merge-key column names.

    Returns:
        ``{"strategy": "scd2", "rows_appended": int, "close_stats": {...}}``.
    """
    now = datetime.now(UTC)
    augmented = _augment_for_scd2(arrow_source, now)

    dt = deltalake.DeltaTable(target_location)
    predicate_close = (
        " AND ".join(f"target.{col} = source.{col}" for col in on)
        + f" AND target.{SCD2_IS_CURRENT} = TRUE"
    )
    close_iso = now.isoformat()
    close_stats = (
        dt.merge(
            source=cast(Any, augmented),
            predicate=predicate_close,
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(
            updates={
                SCD2_VALID_TO: f"TIMESTAMP '{close_iso}'",
                SCD2_IS_CURRENT: "FALSE",
            }
        )
        .execute()
    )

    deltalake.write_deltalake(target_location, cast(Any, augmented), mode="append")
    return {
        "strategy": "scd2",
        "rows_appended": augmented.num_rows,
        "close_stats": close_stats,
    }


def _augment_for_scd2(arrow_source: ArrowTable, now: datetime) -> ArrowTable:
    """Add ``_valid_from`` / ``_valid_to`` / ``_is_current`` to *arrow_source*.

    Args:
        arrow_source: Source rows as a PyArrow Table.
        now: Wall-clock instant to stamp into ``_valid_from``.

    Returns:
        A new Arrow Table with the three SCD-2 columns appended at
        the end (key columns and existing fields are unchanged).
    """
    n = arrow_source.num_rows
    valid_from_col = pa.array([now] * n, type=pa.timestamp("us", tz="UTC"))
    valid_to_col = pa.array([None] * n, type=pa.timestamp("us", tz="UTC"))
    is_current_col = pa.array([True] * n, type=pa.bool_())
    augmented = arrow_source
    augmented = augmented.append_column(SCD2_VALID_FROM, valid_from_col)
    augmented = augmented.append_column(SCD2_VALID_TO, valid_to_col)
    augmented = augmented.append_column(SCD2_IS_CURRENT, is_current_col)
    return augmented
