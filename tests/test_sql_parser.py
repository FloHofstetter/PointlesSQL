"""Unit tests for the SQL parser (extract_table_refs / prepare_sql / classify)."""

from __future__ import annotations

import pytest

from pointlessql.pql.sql_parser import (
    SQLParseError,
    StmtType,
    classify,
    extract_source_refs,
    extract_table_refs,
    extract_write_target,
    parse_and_classify,
    parse_batch,
    prepare_sql,
)


def test_simple_select_extracts_single_ref() -> None:
    refs = extract_table_refs("SELECT * FROM main.sales.orders")
    assert refs == ["main.sales.orders"]


def test_join_extracts_both_refs_in_order() -> None:
    refs = extract_table_refs(
        "SELECT o.* FROM main.sales.orders o JOIN main.sales.customers c ON o.cid = c.id"
    )
    assert refs == ["main.sales.orders", "main.sales.customers"]


def test_cte_alias_is_skipped() -> None:
    # The CTE body reads main.sales.orders; the outer SELECT references
    # the alias ``x`` which must not leak into the enforcement list.
    refs = extract_table_refs("WITH x AS (SELECT * FROM main.sales.orders) SELECT * FROM x")
    assert refs == ["main.sales.orders"]


def test_subquery_reference_is_extracted() -> None:
    refs = extract_table_refs("SELECT * FROM (SELECT * FROM main.sales.orders) q")
    assert refs == ["main.sales.orders"]


def test_duplicate_references_appear_once() -> None:
    refs = extract_table_refs("SELECT a.*, b.* FROM main.sales.orders a, main.sales.orders b")
    assert refs == ["main.sales.orders"]


def test_select_without_tables_returns_empty_list() -> None:
    assert extract_table_refs("SELECT 1 AS n") == []


def test_two_part_reference_raises() -> None:
    with pytest.raises(SQLParseError, match="catalog.schema.table"):
        extract_table_refs("SELECT * FROM sales.orders")


def test_malformed_sql_raises() -> None:
    with pytest.raises(SQLParseError, match="Could not parse SQL"):
        extract_table_refs("SELEC * FROM x")


def test_multi_statement_raises() -> None:
    with pytest.raises(SQLParseError, match="one SQL statement"):
        extract_table_refs("SELECT 1; SELECT 2")


def test_insert_is_rejected_by_extract_table_refs() -> None:
    # extract_table_refs / prepare_sql stay SELECT-only; the dispatcher
    # path uses parse_and_classify for INSERT/UPDATE/DELETE/etc.
    with pytest.raises(SQLParseError, match="SELECT"):
        extract_table_refs("INSERT INTO main.a.b VALUES (1)")


def test_empty_sql_raises() -> None:
    with pytest.raises(SQLParseError, match="Empty"):
        extract_table_refs("")
    with pytest.raises(SQLParseError, match="Empty"):
        extract_table_refs("   \n  ")


def test_prepare_rewrites_three_part_to_quoted_identifier() -> None:
    prepared = prepare_sql("SELECT * FROM main.sales.orders LIMIT 5")
    assert prepared.refs == ["main.sales.orders"]
    # The rewritten form uses a single quoted identifier that
    # DuckDB can bind via conn.register(full_name, ...).
    assert '"main.sales.orders"' in prepared.rewritten_sql
    assert "main.sales.orders" in prepared.rewritten_sql


def test_prepare_preserves_alias() -> None:
    prepared = prepare_sql("SELECT o.id FROM main.sales.orders o WHERE o.id > 0")
    assert prepared.refs == ["main.sales.orders"]
    # Alias ``o`` must survive the rewrite so the column reference
    # ``o.id`` still binds at execution time.
    assert '"main.sales.orders" AS o' in prepared.rewritten_sql


# --- parse_and_classify / classify / extract_write_target ----


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", StmtType.SELECT),
        ("WITH x AS (SELECT * FROM main.s.t) SELECT * FROM x", StmtType.SELECT),
        ("INSERT INTO main.s.t SELECT id FROM main.b.s", StmtType.INSERT_FROM_SELECT),
        ("CREATE TABLE main.s.f AS SELECT * FROM main.b.s", StmtType.CREATE_TABLE_AS),
        ("UPDATE main.s.t SET x = 1 WHERE id = 1", StmtType.UPDATE),
        ("DELETE FROM main.s.t WHERE id = 1", StmtType.DELETE),
        (
            "MERGE INTO main.s.t USING (SELECT id FROM main.b.s) s "
            "ON s.id = t.id WHEN MATCHED THEN UPDATE SET x = s.id",
            StmtType.MERGE,
        ),
        ("DROP TABLE main.s.f", StmtType.DROP_TABLE),
        ("CREATE SCHEMA main.b", StmtType.CREATE_SCHEMA),
        ("DROP SCHEMA main.b CASCADE", StmtType.DROP_SCHEMA),
        ('ALTER TABLE main.s.t SET TBLPROPERTIES("c" = "x")', StmtType.ALTER_TABLE),
    ],
)
def test_classify_dispatches_per_statement_type(sql: str, expected: StmtType) -> None:
    ast, stype = parse_and_classify(sql)
    assert stype is expected
    assert classify(ast) is expected


def test_classify_rejects_bare_create_table() -> None:
    with pytest.raises(SQLParseError, match="Bare CREATE TABLE"):
        parse_and_classify("CREATE TABLE main.s.f (a INT, b TEXT)")


def test_classify_rejects_create_catalog() -> None:
    # sqlglot parses CREATE CATALOG as exp.Command; the editor uses
    # the admin UI for catalog management.
    with pytest.raises(SQLParseError, match="Unsupported statement type"):
        parse_and_classify("CREATE CATALOG hive")


def test_classify_rejects_drop_catalog() -> None:
    with pytest.raises(SQLParseError, match="Unsupported statement type"):
        parse_and_classify("DROP CATALOG hive")


@pytest.mark.parametrize(
    ("sql", "expected_target"),
    [
        ("INSERT INTO main.s.t SELECT id FROM main.b.s", "main.s.t"),
        ("CREATE TABLE main.s.f AS SELECT * FROM main.b.s", "main.s.f"),
        ("UPDATE main.s.t SET x = 1 WHERE id = 1", "main.s.t"),
        ("DELETE FROM main.s.t WHERE id = 1", "main.s.t"),
        (
            "MERGE INTO main.s.t USING main.b.s s ON s.id = t.id "
            "WHEN MATCHED THEN UPDATE SET x = s.id",
            "main.s.t",
        ),
        ("DROP TABLE main.s.f", "main.s.f"),
        ("CREATE SCHEMA main.b", "main.b"),
        ("DROP SCHEMA main.b CASCADE", "main.b"),
        ('ALTER TABLE main.s.t SET TBLPROPERTIES("c" = "x")', "main.s.t"),
    ],
)
def test_extract_write_target_returns_full_fqn(sql: str, expected_target: str) -> None:
    ast, stype = parse_and_classify(sql)
    assert extract_write_target(ast, stype) == expected_target


def test_extract_write_target_raises_for_select() -> None:
    ast, stype = parse_and_classify("SELECT 1")
    with pytest.raises(SQLParseError, match="SELECT has no write target"):
        extract_write_target(ast, stype)


def test_extract_source_refs_excludes_target() -> None:
    ast, stype = parse_and_classify("INSERT INTO main.s.t SELECT id FROM main.b.s")
    assert extract_source_refs(ast, stype) == ["main.b.s"]


def test_extract_source_refs_picks_up_correlated_subquery() -> None:
    ast, stype = parse_and_classify(
        "UPDATE main.s.t SET x = (SELECT max(y) FROM main.b.lookup) WHERE id = 1"
    )
    assert extract_source_refs(ast, stype) == ["main.b.lookup"]


def test_prepare_sql_rejects_non_select_with_pointer() -> None:
    with pytest.raises(SQLParseError, match="parse_and_classify"):
        prepare_sql("INSERT INTO main.s.t SELECT 1")


def test_parse_batch_returns_one_ast_per_statement() -> None:
    asts = parse_batch("SELECT 1; INSERT INTO main.s.t SELECT 2; DELETE FROM main.s.t")
    assert len(asts) == 3
    assert [classify(a) for a in asts] == [
        StmtType.SELECT,
        StmtType.INSERT_FROM_SELECT,
        StmtType.DELETE,
    ]


def test_parse_batch_rejects_empty() -> None:
    with pytest.raises(SQLParseError, match="Empty"):
        parse_batch("")
