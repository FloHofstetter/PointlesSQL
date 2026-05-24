"""End-to-end value-change capture against a real Delta table.

Skips the FastAPI / soyuz / agent-run plumbing and exercises just the
``_capture_value_changes`` helper that
:func:`pointlessql.pql._merge.merge_table` calls after the upsert.
A real Delta table is bootstrapped with CDF on, an upsert flips one
column on one row, and we assert the helper returns exactly one
:class:`ValueChangeSpec`.

These tests are deliberately minimal — broader coverage of the
extract / record / cap logic is in
``tests/test_value_change_capture.py`` and
``tests/test_lineage_values.py``.
"""

from __future__ import annotations

from pathlib import Path

import deltalake
import pyarrow as pa

from pointlessql.pql._cdf import cdf_creation_config
from pointlessql.pql._merge import _capture_value_changes


def _bootstrap_silver_with_cdf(target: Path) -> None:
    """Create a silver-shaped Delta table with three rows + CDF on."""
    rows = pa.table(
        {
            "order_id": ["A", "B", "C"],
            "qty": [1, 2, 3],
            "unit_price": [2.5, 3.0, 4.5],
            "_lineage_row_id": ["row-A", "row-B", "row-C"],
        }
    )
    deltalake.write_deltalake(
        str(target),
        rows,
        configuration=cdf_creation_config(),
    )


def _upsert_one_row(target: Path, *, order_id: str, new_unit_price: float) -> None:
    """Upsert one row with a new unit_price into the existing silver."""
    update = pa.table(
        {
            "order_id": [order_id],
            "qty": [1],
            "unit_price": [new_unit_price],
            "_lineage_row_id": [f"row-{order_id}"],
        }
    )
    dt = deltalake.DeltaTable(str(target))
    dt.merge(
        source=update,
        predicate="target.order_id = source.order_id",
        source_alias="source",
        target_alias="target",
    ).when_matched_update_all().when_not_matched_insert_all().execute()


def test_upsert_with_one_changed_cell_yields_one_spec(tmp_path: Path) -> None:
    target = tmp_path / "silver"
    _bootstrap_silver_with_cdf(target)
    version_before = deltalake.DeltaTable(str(target)).version()

    _upsert_one_row(target, order_id="A", new_unit_price=2.51)

    version_after = deltalake.DeltaTable(str(target)).version()
    assert version_after > version_before

    specs = _capture_value_changes(
        target_location=str(target),
        target="main.silver.orders",
        version_before=version_before,
        version_after=version_after,
    )
    assert specs is not None
    assert len(specs) == 1
    assert specs[0].target_table == "main.silver.orders"
    assert specs[0].target_row_id == "row-A"
    assert specs[0].target_column == "unit_price"
    assert specs[0].old_value == "2.5"
    assert specs[0].new_value == "2.51"


def test_upsert_with_no_change_yields_none(tmp_path: Path) -> None:
    """Re-running the same upsert produces zero value-changes."""
    target = tmp_path / "silver"
    _bootstrap_silver_with_cdf(target)
    version_before = deltalake.DeltaTable(str(target)).version()

    # Upsert with the same values that are already there.
    _upsert_one_row(target, order_id="A", new_unit_price=2.5)

    version_after = deltalake.DeltaTable(str(target)).version()
    specs = _capture_value_changes(
        target_location=str(target),
        target="main.silver.orders",
        version_before=version_before,
        version_after=version_after,
    )
    # Either empty list or None (deltalake may or may not commit a no-op).
    assert specs in (None, [])


def test_capture_skipped_when_versions_unchanged(tmp_path: Path) -> None:
    """Helper returns None when there's no commit range to read."""
    target = tmp_path / "silver"
    _bootstrap_silver_with_cdf(target)
    version = deltalake.DeltaTable(str(target)).version()

    specs = _capture_value_changes(
        target_location=str(target),
        target="main.silver.orders",
        version_before=version,
        version_after=version,
    )
    assert specs is None


def test_capture_skipped_when_versions_missing(tmp_path: Path) -> None:
    """Helper short-circuits when the audit row didn't track versions."""
    target = tmp_path / "silver"
    _bootstrap_silver_with_cdf(target)

    specs = _capture_value_changes(
        target_location=str(target),
        target="main.silver.orders",
        version_before=None,
        version_after=None,
    )
    assert specs is None


def test_pure_insert_yields_no_value_changes(tmp_path: Path) -> None:
    """Inserting a brand-new key produces no preimage/postimage pair."""
    target = tmp_path / "silver"
    _bootstrap_silver_with_cdf(target)
    version_before = deltalake.DeltaTable(str(target)).version()

    _upsert_one_row(target, order_id="Z", new_unit_price=9.99)

    version_after = deltalake.DeltaTable(str(target)).version()
    specs = _capture_value_changes(
        target_location=str(target),
        target="main.silver.orders",
        version_before=version_before,
        version_after=version_after,
    )
    assert specs in (None, [])
