"""Per-cell preimage/postimage diff helper (Sprint 15.7.3).

Pure-function bridge between Delta's Change Data Feed (CDF) PyArrow
output and the :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
shape that ``record_value_changes`` consumes.

The caller hands :func:`extract_value_changes` a CDF PyArrow Table
already filtered to the relevant commit range.  This module
* pairs ``update_preimage`` and ``update_postimage`` events on
  ``_lineage_row_id``,
* skips ``insert`` events (creation, not change),
* skips ``delete`` events (upsert never deletes),
* diffs each pair column-by-column and emits one
  :class:`ValueChangeSpec` per actually-different cell.

Inserts and deletes are explicit no-ops here, not bugs in the upsert
flow — the same helper is reusable for any future primitive that
exposes CDF, and the strict definition keeps the user-facing
question ("what changed in this row?") honest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa

from pointlessql.services.lineage_edges import ValueChangeSpec

CDF_META_COLUMNS = frozenset(
    {
        "_change_type",
        "_commit_version",
        "_commit_timestamp",
    }
)

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"


def extract_value_changes(
    *,
    cdf_table: pa.Table,
    target_table: str,
) -> list[ValueChangeSpec]:
    """Return one :class:`ValueChangeSpec` per actually-different cell.

    Args:
        cdf_table: PyArrow Table produced by
            ``DeltaTable.load_cdf(...).read_all()`` (with the arro3
            → pyarrow conversion already applied).  Must carry the
            ``_change_type`` column plus ``_lineage_row_id`` for
            pairing.
        target_table: Fully-qualified UC name to stamp on each spec.

    Returns:
        A list of ``ValueChangeSpec`` entries.  Empty when the CDF
        stream had no ``update_preimage`` / ``update_postimage``
        pairs, when ``_lineage_row_id`` is missing, or when every
        paired cell turned out to be identical.

        Order is stable but deliberately unspecified beyond the
        guarantee that all changes for one ``(row_id, column)`` pair
        are contiguous — callers that need ordering should sort.
    """
    if cdf_table.num_rows == 0:
        return []

    column_names = set(cdf_table.schema.names)
    if "_change_type" not in column_names or LINEAGE_ROW_ID_COLUMN not in column_names:
        return []

    data = cdf_table.to_pydict()
    change_types: list[str] = data["_change_type"]
    row_ids: list[Any] = data[LINEAGE_ROW_ID_COLUMN]

    diff_columns = sorted(
        column_names - CDF_META_COLUMNS - {LINEAGE_ROW_ID_COLUMN}
    )

    preimages: dict[str, dict[str, Any]] = {}
    postimages: dict[str, dict[str, Any]] = {}
    for i, change_type in enumerate(change_types):
        row_id_raw = row_ids[i]
        if row_id_raw is None:
            continue
        row_id = str(row_id_raw)
        if change_type == "update_preimage":
            preimages[row_id] = {col: data[col][i] for col in diff_columns}
        elif change_type == "update_postimage":
            postimages[row_id] = {col: data[col][i] for col in diff_columns}
        # insert / delete: skipped silently.

    specs: list[ValueChangeSpec] = []
    paired_ids = sorted(set(preimages) & set(postimages))
    for row_id in paired_ids:
        pre = preimages[row_id]
        post = postimages[row_id]
        for column in diff_columns:
            old = pre.get(column)
            new = post.get(column)
            if old == new:
                continue
            specs.append(
                ValueChangeSpec(
                    target_table=target_table,
                    target_row_id=row_id,
                    target_column=column,
                    old_value=None if old is None else str(old),
                    new_value=None if new is None else str(new),
                )
            )
    return specs
