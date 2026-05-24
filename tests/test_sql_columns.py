"""Sqlglot column-lineage extraction unit tests.

Pure-function tests for ``extract_column_lineage`` — no DuckDB,
no soyuz.  The end-to-end ``pql.sql`` path is exercised by the live replay.
"""

from __future__ import annotations

from pointlessql.pql.sql_parser import extract_column_lineage  # noqa: I001

SCHEMA = {
    "main": {
        "silver": {
            "t": {"a": "int", "b": "int", "c": "varchar"},
        }
    }
}


class TestSqlColumnLineage:
    """Per-output-column AST walk classifies edges by transform_kind."""

    def test_simple_select_emits_sql_select(self) -> None:
        edges = extract_column_lineage(
            sql="SELECT a, b FROM main.silver.t",
            schema=SCHEMA,
            output_columns=["a", "b"],
        )
        assert len(edges) == 2
        assert all(e.transform_kind == "sql_select" for e in edges)
        assert all(e.source_table == "main.silver.t" for e in edges)
        assert {e.target_column for e in edges} == {"a", "b"}
        assert {e.source_column for e in edges} == {"a", "b"}
        # Target table is the synthetic constant.
        assert all(e.target_table == "query" for e in edges)

    def test_arithmetic_emits_sql_function_with_detail(self) -> None:
        edges = extract_column_lineage(
            sql="SELECT a + b AS c FROM main.silver.t",
            schema=SCHEMA,
            output_columns=["c"],
        )
        assert len(edges) == 2
        assert all(e.transform_kind == "sql_function" for e in edges)
        assert all(e.target_column == "c" for e in edges)
        # Detail carries the rendered expression.
        details = {e.transform_detail for e in edges}
        assert len(details) == 1
        detail = details.pop()
        assert detail is not None
        assert "a" in detail and "b" in detail and "+" in detail

    def test_count_star_yields_sql_unknown(self) -> None:
        edges = extract_column_lineage(
            sql="SELECT count(*) AS n FROM main.silver.t",
            schema=SCHEMA,
            output_columns=["n"],
        )
        assert len(edges) == 1
        assert edges[0].transform_kind == "sql_unknown"
        assert edges[0].source_table is None
        assert edges[0].source_column is None
        assert edges[0].target_column == "n"

    def test_cte_chain_resolves_to_table(self) -> None:
        edges = extract_column_lineage(
            sql=("WITH x AS (SELECT a FROM main.silver.t) SELECT a FROM x"),
            schema=SCHEMA,
            output_columns=["a"],
        )
        assert len(edges) == 1
        e = edges[0]
        assert e.transform_kind == "sql_select"
        assert e.source_table == "main.silver.t"
        assert e.source_column == "a"

    def test_aliased_simple_column_is_sql_select(self) -> None:
        edges = extract_column_lineage(
            sql="SELECT a AS aa FROM main.silver.t",
            schema=SCHEMA,
            output_columns=["aa"],
        )
        assert len(edges) == 1
        e = edges[0]
        assert e.transform_kind == "sql_select"
        assert e.source_column == "a"
        assert e.target_column == "aa"

    def test_unparseable_sql_returns_empty(self) -> None:
        edges = extract_column_lineage(
            sql="THIS IS NOT SQL ;)",
            schema=SCHEMA,
            output_columns=["whatever"],
        )
        assert edges == []

    def test_custom_target_table(self) -> None:
        edges = extract_column_lineage(
            sql="SELECT a FROM main.silver.t",
            schema=SCHEMA,
            output_columns=["a"],
            target_table="op-42",
        )
        assert all(e.target_table == "op-42" for e in edges)
