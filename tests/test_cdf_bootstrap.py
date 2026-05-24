"""CDF bootstrap helpers.

Verifies that the ``delta.enableChangeDataFeed`` table property is
turned on for new Delta tables — both via the ``configuration={...}``
kwarg path and the retroactive ``set_table_properties`` path that
:func:`pointlessql.pql._cdf.ensure_cdf_enabled` provides.

Lightweight tests: write a tiny Arrow table, check the resulting
DeltaTable's ``metadata().configuration``.  No soyuz, no agent-run
plumbing.
"""

from __future__ import annotations

from pathlib import Path

import deltalake
import pyarrow as pa
import pytest

from pointlessql.pql._cdf import (
    CDF_TBLPROP,
    cdf_creation_config,
    ensure_cdf_enabled,
)


def _read_config(target_location: str) -> dict[str, str]:
    """Return the Delta table's current configuration dict."""
    dt = deltalake.DeltaTable(target_location)
    return dict(dt.metadata().configuration or {})


class TestCdfCreationConfig:
    """``cdf_creation_config`` returns the property dict to pass on create."""

    def test_returns_property_dict(self) -> None:
        cfg = cdf_creation_config()
        assert cfg == {CDF_TBLPROP: "true"}

    def test_pasthrough_to_write_deltalake_enables_cdf(self, tmp_path: Path) -> None:
        target = tmp_path / "t1"
        deltalake.write_deltalake(
            str(target),
            pa.table({"a": [1, 2, 3]}),
            configuration=cdf_creation_config(),
        )
        assert _read_config(str(target)) == {CDF_TBLPROP: "true"}


class TestEnsureCdfEnabled:
    """``ensure_cdf_enabled`` flips the property on existing tables."""

    def test_enables_on_table_without_property(self, tmp_path: Path) -> None:
        target = tmp_path / "t2"
        # Create WITHOUT the configuration kwarg — CDF is off.
        deltalake.write_deltalake(str(target), pa.table({"a": [1]}))
        assert CDF_TBLPROP not in _read_config(str(target))

        ok = ensure_cdf_enabled(str(target))
        assert ok is True
        assert _read_config(str(target))[CDF_TBLPROP] == "true"

    def test_idempotent_on_table_with_property(self, tmp_path: Path) -> None:
        target = tmp_path / "t3"
        deltalake.write_deltalake(
            str(target),
            pa.table({"a": [1]}),
            configuration=cdf_creation_config(),
        )
        before_version = deltalake.DeltaTable(str(target)).version()

        ok = ensure_cdf_enabled(str(target))
        assert ok is True

        # No new commit was issued — version unchanged.
        after_version = deltalake.DeltaTable(str(target)).version()
        assert after_version == before_version

    def test_returns_false_for_missing_path(self, tmp_path: Path) -> None:
        ok = ensure_cdf_enabled(str(tmp_path / "does-not-exist"))
        assert ok is False


@pytest.mark.parametrize(
    "frame",
    [
        pa.table({"x": [1, 2], "y": ["a", "b"]}),
        pa.table({"json_col": ['{"a": 1}', '{"b": 2}']}),
    ],
)
def test_load_cdf_returns_postimage_after_overwrite(tmp_path: Path, frame: pa.Table) -> None:
    """Writing the same table twice with CDF on yields CDF events on read."""
    target = tmp_path / "t4"
    deltalake.write_deltalake(str(target), frame, configuration=cdf_creation_config())
    # Append once — version 1 will have insert events in CDF.
    deltalake.write_deltalake(str(target), frame, mode="append")

    dt = deltalake.DeltaTable(str(target))
    cdf = dt.load_cdf(starting_version=1, ending_version=1)
    # ``load_cdf`` returns an arro3 RecordBatchReader; pyarrow's
    # zero-copy ``pa.table`` constructor accepts it via the PyCapsule
    # interface.
    arrow_chunks = pa.table(cdf.read_all())
    assert arrow_chunks.num_rows >= frame.num_rows
    change_types = set(arrow_chunks.column("_change_type").to_pylist())
    # Pure append → only insert events.
    assert change_types <= {"insert"}
