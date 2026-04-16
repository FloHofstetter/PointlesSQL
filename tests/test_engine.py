"""Engine protocol compliance suite.

Tests are parameterized over engine implementations.  Each engine must
pass the same behavioral contract: read a Delta table, write it back,
and produce correct column metadata for UC registration.
"""

from __future__ import annotations

import deltalake
import duckdb
import pandas as pd
import polars as pl
import pytest

from pointlessql.pql.engine import (
    DuckDBEngine,
    Engine,
    PandasEngine,
    PolarsEngine,
    make_engine,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_ENGINES = [PandasEngine(), DuckDBEngine(), PolarsEngine()]
_ENGINE_IDS = ["pandas", "duckdb", "polars"]


@pytest.fixture(params=_ENGINES, ids=_ENGINE_IDS)
def engine(request: pytest.FixtureRequest) -> Engine:
    """Yield each registered engine in turn."""
    return request.param


@pytest.fixture
def sample_delta(tmp_path):
    """Write a small Delta table for read tests."""
    location = str(tmp_path / "test_table")
    df = pd.DataFrame({
        "id": pd.array([1, 2, 3], dtype="int64"),
        "name": ["alice", "bob", "charlie"],
        "score": pd.array([9.5, 8.0, 7.3], dtype="float64"),
    })
    deltalake.write_deltalake(location, df)
    return location, df


# ------------------------------------------------------------------
# Protocol compliance (parameterized — runs for every engine)
# ------------------------------------------------------------------


class TestEngineProtocol:
    """Every engine must satisfy the Engine protocol."""

    def test_is_engine(self, engine: Engine) -> None:
        assert isinstance(engine, Engine)

    def test_read_returns_data(self, engine: Engine, sample_delta) -> None:
        location, _ = sample_delta
        result = engine.read(location)
        assert result is not None

    def test_write_round_trip(self, engine: Engine, sample_delta, tmp_path) -> None:
        location, _ = sample_delta
        frame = engine.read(location)

        out_location = str(tmp_path / "output_table")
        engine.write(frame, out_location, "overwrite")

        # Verify with deltalake directly.
        dt = deltalake.DeltaTable(out_location)
        result_df = dt.to_pandas()
        assert len(result_df) == 3
        assert set(result_df.columns) == {"id", "name", "score"}

    def test_columns_info_shape(self, engine: Engine, sample_delta) -> None:
        location, _ = sample_delta
        frame = engine.read(location)
        cols = engine.columns_info(frame)
        assert len(cols) == 3
        for name, type_name, type_text, nullable in cols:
            assert isinstance(name, str)
            assert isinstance(type_name, str)
            assert isinstance(type_text, str)
            assert isinstance(nullable, bool)

    def test_columns_info_names(self, engine: Engine, sample_delta) -> None:
        location, _ = sample_delta
        frame = engine.read(location)
        cols = engine.columns_info(frame)
        names = [c[0] for c in cols]
        assert names == ["id", "name", "score"]

    def test_columns_info_types(self, engine: Engine, sample_delta) -> None:
        location, _ = sample_delta
        frame = engine.read(location)
        cols = engine.columns_info(frame)
        col_map = {c[0]: (c[1], c[2]) for c in cols}
        assert col_map["id"] == ("LONG", "long")
        assert col_map["score"] == ("DOUBLE", "double")
        assert col_map["name"] == ("STRING", "string")


# ------------------------------------------------------------------
# make_engine factory
# ------------------------------------------------------------------


class TestMakeEngine:
    def test_pandas(self) -> None:
        engine = make_engine("pandas")
        assert isinstance(engine, PandasEngine)

    def test_duckdb(self) -> None:
        engine = make_engine("duckdb")
        assert isinstance(engine, DuckDBEngine)

    def test_polars(self) -> None:
        engine = make_engine("polars")
        assert isinstance(engine, PolarsEngine)

    def test_case_insensitive(self) -> None:
        engine = make_engine("Pandas")
        assert isinstance(engine, PandasEngine)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            make_engine("spark")


# ------------------------------------------------------------------
# Engine-specific tests
# ------------------------------------------------------------------


class TestPandasEngineSpecific:
    def test_read_returns_dataframe(self, sample_delta) -> None:
        engine = PandasEngine()
        location, expected_df = sample_delta
        result = engine.read(location)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        pd.testing.assert_frame_equal(
            result.sort_values("id").reset_index(drop=True),
            expected_df.sort_values("id").reset_index(drop=True),
        )


class TestDuckDBEngineSpecific:
    def test_read_returns_relation(self, sample_delta) -> None:
        engine = DuckDBEngine()
        location, _ = sample_delta
        result = engine.read(location)
        assert isinstance(result, duckdb.DuckDBPyRelation)

    def test_relation_fetchall(self, sample_delta) -> None:
        engine = DuckDBEngine()
        location, _ = sample_delta
        result = engine.read(location)
        rows = result.fetchall()
        assert len(rows) == 3

    def test_write_from_relation(self, sample_delta, tmp_path) -> None:
        engine = DuckDBEngine()
        location, expected_df = sample_delta
        rel = engine.read(location)

        out = str(tmp_path / "duckdb_out")
        engine.write(rel, out, "overwrite")

        dt = deltalake.DeltaTable(out)
        result_df = dt.to_pandas()
        assert len(result_df) == 3
        assert set(result_df.columns) == {"id", "name", "score"}


class TestPolarsEngineSpecific:
    def test_read_returns_polars_dataframe(self, sample_delta) -> None:
        engine = PolarsEngine()
        location, _ = sample_delta
        result = engine.read(location)
        assert isinstance(result, pl.DataFrame)

    def test_dataframe_content(self, sample_delta) -> None:
        engine = PolarsEngine()
        location, expected_df = sample_delta
        result = engine.read(location)
        assert result.shape == (3, 3)
        assert set(result.columns) == {"id", "name", "score"}
        assert sorted(result["id"].to_list()) == [1, 2, 3]

    def test_write_from_polars(self, sample_delta, tmp_path) -> None:
        engine = PolarsEngine()
        location, _ = sample_delta
        frame = engine.read(location)

        out = str(tmp_path / "polars_out")
        engine.write(frame, out, "overwrite")

        dt = deltalake.DeltaTable(out)
        result_df = dt.to_pandas()
        assert len(result_df) == 3
        assert set(result_df.columns) == {"id", "name", "score"}
