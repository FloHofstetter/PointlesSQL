"""Pure-function unit tests for ``extract_value_changes``.

Synthesises CDF-shaped PyArrow Tables (with ``_change_type``,
``_lineage_row_id``, and arbitrary data columns) and asserts that the
diff helper:

* pairs ``update_preimage`` / ``update_postimage`` events on
  ``_lineage_row_id``,
* skips ``insert`` and ``delete`` events,
* skips cells where preimage equals postimage,
* preserves NULL values as Python ``None``,
* survives missing ``_lineage_row_id`` (returns empty list).

No deltalake calls — these tests are designed to land on every CI
run in milliseconds.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pointlessql.services.value_change_capture import extract_value_changes


def _cdf_table(rows: list[dict]) -> pa.Table:
    """Build a CDF-shaped PyArrow Table from per-row dicts."""
    if not rows:
        return pa.table(
            {
                "_change_type": pa.array([], type=pa.string()),
                "_lineage_row_id": pa.array([], type=pa.string()),
            }
        )
    columns: dict[str, list] = {key: [] for key in rows[0]}
    for row in rows:
        for key in columns:
            columns[key].append(row.get(key))
    return pa.table(columns)


class TestExtractValueChanges:
    """Diff helper produces one spec per actually-different cell."""

    def test_one_changed_column_yields_one_spec(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                    "unit_price": 2.5,
                },
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                    "unit_price": 2.51,
                },
            ]
        )
        specs = extract_value_changes(cdf_table=cdf, target_table="t")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.target_table == "t"
        assert spec.target_row_id == "r1"
        assert spec.target_column == "unit_price"
        assert spec.old_value == "2.5"
        assert spec.new_value == "2.51"

    def test_two_changed_columns_yields_two_specs(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                    "unit_price": 2.5,
                },
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": "r1",
                    "qty": 5,
                    "unit_price": 2.51,
                },
            ]
        )
        specs = extract_value_changes(cdf_table=cdf, target_table="t")
        assert len(specs) == 2
        cols = {s.target_column for s in specs}
        assert cols == {"qty", "unit_price"}

    def test_inserts_are_skipped(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "insert",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                },
                {
                    "_change_type": "insert",
                    "_lineage_row_id": "r2",
                    "qty": 5,
                },
            ]
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_deletes_are_skipped(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "delete",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                },
            ]
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_unchanged_cells_skipped(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                    "unit_price": 2.5,
                },
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,  # unchanged → skipped
                    "unit_price": 2.5,  # unchanged → skipped
                },
            ]
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_null_old_value_passes_through(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "comment": None,
                },
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": "r1",
                    "comment": "new note",
                },
            ]
        )
        specs = extract_value_changes(cdf_table=cdf, target_table="t")
        assert len(specs) == 1
        assert specs[0].old_value is None
        assert specs[0].new_value == "new note"

    def test_null_to_null_skipped(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "comment": None,
                },
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": "r1",
                    "comment": None,
                },
            ]
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_unpaired_preimage_skipped(self) -> None:
        cdf = _cdf_table(
            [
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": "r1",
                    "qty": 1,
                },
                # No matching postimage for r1.
            ]
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_empty_cdf_returns_empty(self) -> None:
        cdf = _cdf_table([])
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    def test_missing_lineage_row_id_returns_empty(self) -> None:
        cdf = pa.table(
            {
                "_change_type": pa.array(["update_preimage"], type=pa.string()),
                "qty": pa.array([1]),
            }
        )
        assert extract_value_changes(cdf_table=cdf, target_table="t") == []

    @pytest.mark.parametrize("change_count", [3, 7, 50])
    def test_multiple_rows_each_with_change(self, change_count: int) -> None:
        rows: list[dict] = []
        for i in range(change_count):
            rows.append(
                {
                    "_change_type": "update_preimage",
                    "_lineage_row_id": f"r{i}",
                    "qty": i,
                }
            )
            rows.append(
                {
                    "_change_type": "update_postimage",
                    "_lineage_row_id": f"r{i}",
                    "qty": i + 100,
                }
            )
        specs = extract_value_changes(cdf_table=_cdf_table(rows), target_table="t")
        assert len(specs) == change_count
        assert {s.target_column for s in specs} == {"qty"}
