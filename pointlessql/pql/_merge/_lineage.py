# pyright: reportUnusedFunction=false, reportPrivateUsage=false
"""Lineage helpers: row-id prep, reject detection, value-change capture."""

from __future__ import annotations

import logging
from typing import Any, cast

import deltalake
import pyarrow as pa

from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.pql._types import ArrowArray, ArrowTable
from pointlessql.services.lineage_edges import synth_target_row_id

logger = logging.getLogger(__name__)


def _capture_value_changes(
    *,
    target_location: str,
    target: str,
    version_before: int | None,
    version_after: int | None,
) -> list[Any] | None:
    """Best-effort capture of per-cell value changes from Delta CDF.

    runs after ``_do_upsert`` returns and the audit
    row has its delta_version_before / delta_version_after stamped.
    assumes the caller already enabled CDF on the
    target before ``_do_upsert`` (so the merge commit lands with CDF
    on); this helper just reads the stream and pairs events.  Any
    failure (deltalake error, missing ``_lineage_row_id``) is logged
    at INFO and returns ``None`` so the merge that already committed
    never rolls back.

    Args:
        target_location: Delta table URI.
        target: Fully-qualified UC name to stamp on each spec.
        version_before: Recorder-side Delta version pre-merge, or
            ``None`` when the audit hook didn't fire.
        version_after: Recorder-side Delta version post-merge, or
            ``None``.

    Returns:
        A list of
        :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
        entries, or ``None`` when capture was impossible / yielded
        nothing.
    """
    if version_before is None or version_after is None:
        return None
    if version_after <= version_before:
        return None

    # CDF is now bootstrapped before ``_do_upsert`` (see
    # ``merge_table``), so the merge commit always lands with CDF on
    # — no post-merge ALTER needed here.

    try:
        from pointlessql.services.value_change_capture import extract_value_changes

        dt = deltalake.DeltaTable(target_location)
        cdf_reader = dt.load_cdf(
            starting_version=version_before + 1,
            ending_version=version_after,
        )
        cdf_arrow = pa.table(cdf_reader.read_all())
    except Exception:  # noqa: BLE001 — best-effort
        logger.info(
            "value-change capture: load_cdf failed for %s",
            target_location,
            exc_info=True,
        )
        return None

    specs = extract_value_changes(cdf_table=cdf_arrow, target_table=target)
    return specs or None


def _detect_rejects(
    arrow_source: ArrowTable, on: list[str]
) -> tuple[ArrowTable, list[tuple[str, str, str | None]]]:
    """Identify pre-merge reject rows and return the cleaned source.

    opt-in via ``track_rejects=True``.  Only two
    reject reasons are detectable pre-merge without inspecting the
    target Delta state:

    * ``on_key_null`` — any row whose ``on`` columns contain NULL.
      The Delta-merge predicate evaluates NULL = NULL as false, so
      these rows always insert; usually this is unintended.
    * ``duplicate_in_source`` — rows that share the same ``on``
      values within the source.  A merge with such a source is
      undefined behaviour in deltalake — last-write-wins semantics
      depend on partitioning order.  We keep the first occurrence
      and reject the rest.

    Schema-mismatch and merge-predicate-excluded reasons need
    target-side context that the helper deliberately does not
    pull in here; callers that need them surface the rejects via
    ``pending_rejects`` with reason ``"other"`` from their own
    error-handling paths.

    Args:
        arrow_source: Source PyArrow Table.  When it has no
            ``_lineage_row_id`` column, no rejects can be tied to a
            source row, so the function returns the table unchanged
            with an empty rejects list.
        on: Merge-key column names.

    Returns:
        ``(cleaned_source, rejects)``.  ``cleaned_source`` has the
        rejected rows removed; the merge proceeds with this
        narrower table.  ``rejects`` is a list of
        ``(source_row_id, reason, detail)`` tuples in source order.
        Empty list when the source had no rejects.
    """
    if LINEAGE_ROW_ID_COLUMN not in arrow_source.schema.names:
        return arrow_source, []

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover — pandas is a hard dep
        return arrow_source, []

    df: pd.DataFrame = arrow_source.to_pandas()
    rejects: list[tuple[str, str, str | None]] = []
    keep_mask = pd.Series([True] * len(df), index=df.index)

    null_key_mask = pd.Series([False] * len(df), index=df.index)
    for col in on:
        if col in df.columns:
            null_key_mask = null_key_mask | df[col].isna()

    for idx in df.index[null_key_mask]:
        row_id = df.at[idx, LINEAGE_ROW_ID_COLUMN]
        first_null = next(
            (col for col in on if col in df.columns and pd.isna(df.at[idx, col])),
            None,
        )
        rejects.append(
            (
                str(row_id) if row_id is not None else "",
                "on_key_null",
                f"NULL in on-key column {first_null!r}" if first_null else None,
            )
        )
    keep_mask = keep_mask & ~null_key_mask

    surviving = cast("pd.DataFrame", df[keep_mask])
    dup_mask = surviving.duplicated(subset=on, keep="first")
    for idx in surviving.index[dup_mask]:
        row_id = surviving.at[idx, LINEAGE_ROW_ID_COLUMN]
        key_repr = ", ".join(f"{c}={surviving.at[idx, c]!r}" for c in on if c in surviving.columns)
        rejects.append(
            (
                str(row_id) if row_id is not None else "",
                "duplicate_in_source",
                f"second occurrence of merge key ({key_repr})",
            )
        )

    final_mask = keep_mask.copy()
    final_mask.loc[surviving.index[dup_mask]] = False
    cleaned_df = df[final_mask].reset_index(drop=True)

    return (
        cast(ArrowTable, pa.Table.from_pandas(cleaned_df, preserve_index=False)),
        rejects,
    )


def _prepare_lineage(
    arrow_source: ArrowTable, target: str
) -> tuple[list[str], list[str], ArrowTable]:
    """Extract source ``_lineage_row_id`` values and synthesise target IDs.

    When the source has a ``_lineage_row_id`` column the target gets
    a deterministic per-row ID written into the same column so the
    chain stays connected.  When the source has no such column the
    helper is a no-op — the target table simply doesn't gain a
    lineage column for the rows from this merge, and 's
    walk-back stops there with a "lineage break" marker.

    Args:
        arrow_source: PyArrow Table fed into the merge.
        target: Fully-qualified UC name of the merge target.

    Returns:
        ``(source_row_ids, target_row_ids, arrow_source_with_target_ids)``.
        Both lists are empty when the source doesn't carry a lineage
        column — caller skips edge emission.
    """
    if LINEAGE_ROW_ID_COLUMN not in arrow_source.schema.names:
        return [], [], arrow_source

    column = arrow_source.column(LINEAGE_ROW_ID_COLUMN)
    source_row_ids: list[str] = [v if isinstance(v, str) else "" for v in column.to_pylist()]
    target_row_ids = [synth_target_row_id(src, target) if src else "" for src in source_row_ids]
    target_array = cast(ArrowArray, pa.array(target_row_ids, type=pa.string()))
    rebuilt = arrow_source.set_column(
        arrow_source.schema.get_field_index(LINEAGE_ROW_ID_COLUMN),
        LINEAGE_ROW_ID_COLUMN,
        target_array,
    )
    return source_row_ids, target_row_ids, rebuilt
