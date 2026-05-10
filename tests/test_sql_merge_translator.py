"""Unit tests for the Phase-63.5 MERGE AST translator.

Validates that:

* Supported MERGE shapes parse cleanly: simple upsert (single
  WHEN MATCHED THEN UPDATE), upsert with INSERT clause, and
  ON predicates with AND-combined column equality.
* Unsupported MERGE shapes raise :class:`SQLMergeUnsupportedError`
  with structured guidance: per-clause AND condition, multiple
  WHEN MATCHED branches, WHEN MATCHED THEN DELETE,
  WHEN NOT MATCHED BY SOURCE, missing WHEN MATCHED.
* Source extraction works for both plain table refs and USING
  subqueries (subquery materialisation is mocked — we only care
  the right helper is called).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import deltalake
import duckdb
import pyarrow as pa
import pytest
import sqlglot

from pointlessql.pql.sql_merge_translator import (
    MergeCallSpec,
    SQLMergeUnsupportedError,
    translate_merge_ast,
)
from pointlessql.pql.sql_parser import parse_and_classify


def _parse_merge(sql: str):
    """Helper: parse a MERGE statement and return its sqlglot Merge AST."""
    ast, _ = parse_and_classify(sql)
    import sqlglot.expressions as exp

    assert isinstance(ast, exp.Merge), f"expected Merge, got {type(ast).__name__}"
    return ast


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


@pytest.fixture
def silver_delta(tmp_path: Path) -> str:
    """Create a small Delta table the translator can read directly."""
    loc = str(tmp_path / "silver")
    table = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    deltalake.write_deltalake(loc, table)
    return loc


# ─── Supported shapes ────────────────────────────────────────────────


def test_simple_upsert_parses(
    conn: duckdb.DuckDBPyConnection, silver_delta: str
) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET name = s.name "
        "WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name)"
    )
    ast = _parse_merge(sql)
    spec = translate_merge_ast(
        ast,
        conn=conn,
        approved={"main.bronze.staging": silver_delta},
    )
    assert isinstance(spec, MergeCallSpec)
    assert spec.target == "main.silver.orders"
    assert spec.on == ["id"]
    assert spec.strategy == "upsert"
    assert spec.source_df is not None


def test_upsert_without_insert_clause_parses(
    conn: duckdb.DuckDBPyConnection, silver_delta: str
) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET name = s.name"
    )
    ast = _parse_merge(sql)
    spec = translate_merge_ast(
        ast,
        conn=conn,
        approved={"main.bronze.staging": silver_delta},
    )
    assert spec.on == ["id"]


def test_and_combined_on_predicate_parses(
    conn: duckdb.DuckDBPyConnection, silver_delta: str
) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id AND t.name = s.name "
        "WHEN MATCHED THEN UPDATE SET name = s.name"
    )
    ast = _parse_merge(sql)
    spec = translate_merge_ast(
        ast,
        conn=conn,
        approved={"main.bronze.staging": silver_delta},
    )
    assert spec.on == ["id", "name"]


# ─── Unsupported shapes ──────────────────────────────────────────────


def test_per_clause_condition_rejected(conn: duckdb.DuckDBPyConnection) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN MATCHED AND s.name IS NOT NULL THEN UPDATE SET name = s.name"
    )
    ast = _parse_merge(sql)
    with pytest.raises(SQLMergeUnsupportedError, match="per-clause AND condition"):
        translate_merge_ast(ast, conn=conn, approved={})


def test_when_matched_then_delete_rejected(conn: duckdb.DuckDBPyConnection) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN MATCHED THEN DELETE"
    )
    ast = _parse_merge(sql)
    with pytest.raises(SQLMergeUnsupportedError, match="THEN UPDATE"):
        translate_merge_ast(ast, conn=conn, approved={})


def test_complex_predicate_rejected(conn: duckdb.DuckDBPyConnection) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id > s.id "
        "WHEN MATCHED THEN UPDATE SET name = s.name"
    )
    ast = _parse_merge(sql)
    with pytest.raises(SQLMergeUnsupportedError, match="column = column"):
        translate_merge_ast(ast, conn=conn, approved={})


def test_missing_when_matched_rejected(conn: duckdb.DuckDBPyConnection) -> None:
    sql = (
        "MERGE INTO main.silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name)"
    )
    ast = _parse_merge(sql)
    with pytest.raises(SQLMergeUnsupportedError, match="WHEN MATCHED THEN UPDATE"):
        translate_merge_ast(ast, conn=conn, approved={})


def test_subquery_source_routes_through_materialisation(
    conn: duckdb.DuckDBPyConnection, silver_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """USING (SELECT …) → _materialise_select_to_pandas is invoked."""
    fake_df = pa.table({"id": [1], "name": ["x"]}).to_pandas()
    fake_helper = MagicMock(return_value=fake_df)
    monkeypatch.setattr(
        "pointlessql.api.pql_write_routes._materialise_select_to_pandas",
        fake_helper,
    )

    sql = (
        "MERGE INTO main.silver.orders t "
        "USING (SELECT id, name FROM main.bronze.staging) s "
        "ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET name = s.name"
    )
    ast = _parse_merge(sql)
    spec = translate_merge_ast(
        ast,
        conn=conn,
        approved={"main.bronze.staging": silver_delta},
    )
    assert spec.source_df is fake_df
    fake_helper.assert_called_once()


def test_unqualified_target_rejected(conn: duckdb.DuckDBPyConnection) -> None:
    """Two-part target raises SQLParseError (caught as base class)."""
    sql = (
        "MERGE INTO silver.orders t "
        "USING main.bronze.staging s "
        "ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET name = s.name"
    )
    # sqlglot may parse this — the translator should reject the
    # 2-part target.
    ast = sqlglot.parse_one(sql, dialect="duckdb")
    import sqlglot.expressions as exp

    if not isinstance(ast, exp.Merge):
        pytest.skip("sqlglot did not produce a Merge AST for this input")

    from pointlessql.pql.sql_parser import SQLParseError

    with pytest.raises(SQLParseError, match="fully qualified"):
        translate_merge_ast(ast, conn=conn, approved={})
