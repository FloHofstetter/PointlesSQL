"""Regression test for the Sprint 13.11.11 schema-overwrite bug.

The 2026-04-26 walkthrough's gpt-5-mini run hit this:

    SchemaMismatchError: Cannot cast schema, number of fields does
    not match: 5 vs 6

…when ``pql.write_table(df, target, mode="overwrite")`` ran against
an existing Delta table whose schema had a different column count.
``deltalake.write_deltalake`` refuses any column-set change unless
``schema_mode="overwrite"`` is passed alongside ``mode="overwrite"``,
and the engine layer wasn't doing that.

This test pins the post-fix behaviour: an overwrite that changes the
column count succeeds, and the resulting Delta table reflects the
new schema.
"""

from __future__ import annotations

from pathlib import Path

import deltalake
import pandas as pd

from pointlessql.pql import DuckDBEngine, PandasEngine, PolarsEngine


def test_pandas_overwrite_replaces_schema(tmp_path: Path) -> None:
    """Pandas engine: overwrite with fewer columns must succeed."""
    loc = str(tmp_path / "tbl")
    initial = pd.DataFrame({"a": [1, 2], "b": ["x", "y"], "c": [10.0, 20.0]})
    deltalake.write_deltalake(loc, initial)

    engine = PandasEngine()
    new_frame = pd.DataFrame({"a": [3, 4], "b": ["z", "w"]})  # 2 cols, was 3
    engine.write(new_frame, loc, "overwrite")

    after = deltalake.DeltaTable(loc).to_pandas()
    assert list(after.columns) == ["a", "b"]
    assert len(after) == 2


def test_pandas_overwrite_adds_column(tmp_path: Path) -> None:
    """Pandas engine: overwrite with extra column must succeed."""
    loc = str(tmp_path / "tbl")
    deltalake.write_deltalake(loc, pd.DataFrame({"a": [1, 2]}))

    engine = PandasEngine()
    engine.write(pd.DataFrame({"a": [3, 4], "b": ["new", "col"]}), loc, "overwrite")

    after = deltalake.DeltaTable(loc).to_pandas()
    assert set(after.columns) == {"a", "b"}


def test_pandas_append_still_requires_matching_schema(tmp_path: Path) -> None:
    """Append must still match — that's the point of append."""
    import pytest

    loc = str(tmp_path / "tbl")
    deltalake.write_deltalake(loc, pd.DataFrame({"a": [1]}))

    engine = PandasEngine()
    with pytest.raises(Exception):  # noqa: B017,PT011 — deltalake's own error type  # pyright: ignore[reportUnusedCallResult]
        engine.write(pd.DataFrame({"a": [2], "b": ["mismatch"]}), loc, "append")


def test_duckdb_overwrite_replaces_schema(tmp_path: Path) -> None:
    """DuckDB engine: overwrite with different column count must succeed."""
    loc = str(tmp_path / "tbl")
    deltalake.write_deltalake(loc, pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}))

    engine = DuckDBEngine()
    relation = engine._conn.from_query("SELECT 9 AS only_col")  # type: ignore[reportPrivateUsage]
    engine.write(relation, loc, "overwrite")

    after = deltalake.DeltaTable(loc).to_pandas()
    assert list(after.columns) == ["only_col"]


def test_polars_overwrite_replaces_schema(tmp_path: Path) -> None:
    """Polars engine: overwrite with different column count must succeed."""
    import polars as pl

    loc = str(tmp_path / "tbl")
    deltalake.write_deltalake(loc, pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}))

    engine = PolarsEngine()
    new_frame = pl.DataFrame({"only_col": [42]})
    engine.write(new_frame, loc, "overwrite")

    after = deltalake.DeltaTable(loc).to_pandas()
    assert list(after.columns) == ["only_col"]
