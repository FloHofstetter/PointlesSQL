"""Mutation-killing tests for the per-kind DuckDB reader builders.

The connector builders are pure: ``(kind, config, secrets)`` in, a
:class:`ReaderSpec` (sql + required extensions + single-table marker)
out.  These tests pin the generated SQL, the required-extension
tuples, the path/identifier quoting and the validation errors for
every connector kind.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.models.ingest import INGEST_SOURCE_KINDS
from pointlessql.services.ingest.connectors import (
    ReaderSpec,
    _file_reader_for_path,
    _split_qualified_table,
    build_reader_spec,
    build_table_listing_spec,
    quote_sql_identifier,
    quote_sql_string,
)

# --- quoting --------------------------------------------------------------


def test_quote_sql_string_wraps_and_doubles_quotes() -> None:
    assert quote_sql_string("foo") == "'foo'"
    assert quote_sql_string("foo'bar") == "'foo''bar'"


def test_quote_sql_identifier_wraps_and_doubles_double_quotes() -> None:
    assert quote_sql_identifier("col") == '"col"'
    assert quote_sql_identifier('a"b') == '"a""b"'


# --- _file_reader_for_path ------------------------------------------------


@pytest.mark.parametrize(
    "path,reader",
    [
        ("/d/x.parquet", "read_parquet"),
        ("/d/x.csv", "read_csv_auto"),
        ("/d/x.json", "read_json_auto"),
        ("/d/x.jsonl", "read_json_auto"),
        ("/d/x.ndjson", "read_json_auto"),
        ("/d/x.PARQUET", "read_parquet"),  # case-insensitive
    ],
)
def test_file_reader_for_path_picks_reader(path: str, reader: str) -> None:
    assert _file_reader_for_path(path)[0] == reader


def test_file_reader_for_path_returns_basename() -> None:
    assert _file_reader_for_path("/a/b/c.csv") == ("read_csv_auto", "c.csv")


def test_file_reader_for_path_unknown_extension_raises() -> None:
    with pytest.raises(ValidationError, match="Cannot pick a DuckDB reader"):
        _file_reader_for_path("/a/b.txt")


# --- _split_qualified_table -----------------------------------------------


def test_split_qualified_table_bare_uses_default_schema() -> None:
    assert _split_qualified_table("t", default_schema="public") == ("public", "t")


def test_split_qualified_table_two_part() -> None:
    assert _split_qualified_table("sales.orders", default_schema="public") == (
        "sales",
        "orders",
    )


def test_split_qualified_table_three_part_raises() -> None:
    with pytest.raises(ValidationError, match="schema.table"):
        _split_qualified_table("a.b.c", default_schema="public")


# --- build_reader_spec: file-based ----------------------------------------


def test_reader_file_upload() -> None:
    spec = build_reader_spec("file_upload", {"path": "/data/x.csv"})
    assert spec.sql == "SELECT * FROM read_csv_auto('/data/x.csv')"
    assert spec.install == ()
    assert spec.single_table_name == "x.csv"


def test_reader_file_upload_missing_path_raises() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("file_upload", {})
    assert str(ei.value) == "file_upload source requires 'path' in config."


def test_reader_parquet_glob() -> None:
    spec = build_reader_spec("parquet_glob", {"pattern": "/d/*.parquet"})
    assert spec.sql == "SELECT * FROM read_parquet('/d/*.parquet')"
    assert spec.single_table_name == "*.parquet"


def test_reader_parquet_glob_missing_pattern_raises() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("parquet_glob", {})
    assert str(ei.value) == "parquet_glob source requires 'pattern' in config."


def test_reader_http_uses_httpfs() -> None:
    spec = build_reader_spec("http", {"url": "https://h/d.parquet"})
    assert spec.sql == "SELECT * FROM read_parquet('https://h/d.parquet')"
    assert spec.install == ("httpfs",)
    assert spec.single_table_name == "d.parquet"


def test_reader_s3_uses_httpfs() -> None:
    spec = build_reader_spec("s3", {"url": "s3://b/k.csv"})
    assert spec.sql == "SELECT * FROM read_csv_auto('s3://b/k.csv')"
    assert spec.install == ("httpfs",)


def test_reader_http_missing_url_exact_message() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("http", {})
    assert str(ei.value) == "http source requires 'url' in config."


def test_reader_s3_missing_url_exact_message() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("s3", {})
    assert str(ei.value) == "s3 source requires 'url' in config."


# --- build_reader_spec: SQL connectors ------------------------------------


def test_reader_postgres_full_sql_and_escaping() -> None:
    spec = build_reader_spec(
        "postgres",
        {"host": "h", "db": "d", "user": "u", "port": 5444},
        {"password": "p'q"},
        "s.t",
    )
    assert spec.sql == (
        "SELECT * FROM postgres_scan('host=h port=5444 dbname=d user=u password=p''q', 's', 't')"
    )
    assert spec.install == ("postgres",)


def test_reader_postgres_default_port_5432() -> None:
    spec = build_reader_spec("postgres", {"host": "h", "db": "d", "user": "u"}, {}, "t")
    assert "port=5432" in spec.sql


def test_reader_postgres_requires_source_table() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("postgres", {"host": "h", "db": "d", "user": "u"}, {})
    assert str(ei.value) == "postgres source requires 'source_table' (schema.table)."


def test_reader_postgres_requires_host_db_user() -> None:
    with pytest.raises(ValidationError, match="'host', 'db', and 'user'"):
        build_reader_spec("postgres", {"host": "h"}, {}, "t")


def test_reader_mysql_full_sql() -> None:
    spec = build_reader_spec(
        "mysql", {"host": "h", "db": "d", "user": "u"}, {"password": "p"}, "s.t"
    )
    assert spec.sql == (
        "SELECT * FROM mysql_scan('host=h port=3306 database=d user=u password=p', 's', 't')"
    )
    assert spec.install == ("mysql",)


def test_reader_sqlite_full_sql() -> None:
    spec = build_reader_spec("sqlite", {"path": "/db.sqlite"}, None, "tbl")
    assert spec.sql == "SELECT * FROM sqlite_scan('/db.sqlite', 'tbl')"
    assert spec.install == ("sqlite",)


def test_reader_sqlite_requires_path() -> None:
    with pytest.raises(ValidationError) as ei:
        build_reader_spec("sqlite", {}, None, "tbl")
    assert str(ei.value) == "sqlite source requires 'path' in config."


def test_reader_unknown_kind_raises() -> None:
    with pytest.raises(ValidationError, match="Unknown ingest source kind"):
        build_reader_spec("redshift", {})


# --- build_table_listing_spec ---------------------------------------------


@pytest.mark.parametrize("kind", ["file_upload", "parquet_glob", "http", "s3"])
def test_listing_file_kinds_short_circuit(kind: str) -> None:
    config: dict[str, Any] = (
        {"pattern": "/d/*.parquet"}
        if kind == "parquet_glob"
        else {"url": "https://h/d.csv"}
        if kind in ("http", "s3")
        else {"path": "/d/x.csv"}
    )
    spec = build_table_listing_spec(kind, config)
    assert spec.sql == "SELECT 1 WHERE 1=0"
    assert spec.single_table_name is not None


def test_listing_http_carries_httpfs_install() -> None:
    spec = build_table_listing_spec("http", {"url": "https://h/d.csv"})
    assert spec.install == ("httpfs",)


def test_listing_postgres_attaches_and_queries_information_schema() -> None:
    spec = build_table_listing_spec("postgres", {"host": "h", "db": "d", "user": "u"})
    assert spec.sql == (
        "ATTACH 'host=h port=5432 dbname=d user=u password=' AS _pql_src "
        "(TYPE postgres, READ_ONLY); "
        "SELECT table_schema || '.' || table_name AS name "
        "FROM _pql_src.information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
        "ORDER BY 1; "
        "DETACH _pql_src;"
    )
    assert spec.install == ("postgres",)


def test_listing_postgres_requires_host_db_user() -> None:
    with pytest.raises(ValidationError, match="'host', 'db', and 'user'"):
        build_table_listing_spec("postgres", {"host": "h"})


def test_listing_postgres_custom_port() -> None:
    spec = build_table_listing_spec("postgres", {"host": "h", "db": "d", "user": "u", "port": 6000})
    assert "port=6000" in spec.sql


def test_listing_mysql_full_sql() -> None:
    spec = build_table_listing_spec("mysql", {"host": "h", "db": "d", "user": "u"})
    assert spec.sql == (
        "ATTACH 'host=h port=3306 database=d user=u password=' AS _pql_src "
        "(TYPE mysql, READ_ONLY); "
        "SELECT table_schema || '.' || table_name AS name "
        "FROM _pql_src.information_schema.tables "
        "WHERE table_schema NOT IN "
        "('mysql','information_schema','sys','performance_schema') "
        "ORDER BY 1; "
        "DETACH _pql_src;"
    )
    assert spec.install == ("mysql",)


def test_listing_sqlite_queries_sqlite_master() -> None:
    spec = build_table_listing_spec("sqlite", {"path": "/db.sqlite"})
    assert spec.sql == (
        "ATTACH '/db.sqlite' AS _pql_src (TYPE sqlite, READ_ONLY); "
        "SELECT name FROM _pql_src.sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY 1; "
        "DETACH _pql_src;"
    )
    assert spec.install == ("sqlite",)


def test_listing_sqlite_requires_path() -> None:
    with pytest.raises(ValidationError, match="sqlite source requires 'path'"):
        build_table_listing_spec("sqlite", {})


def test_listing_unknown_kind_raises() -> None:
    with pytest.raises(ValidationError, match="Unknown ingest source kind"):
        build_table_listing_spec("redshift", {})


# --- module wiring --------------------------------------------------------


def test_reader_spec_is_frozen_slots_dataclass() -> None:
    spec = ReaderSpec(sql="SELECT 1")
    assert spec.install == () and spec.single_table_name is None
    with pytest.raises((AttributeError, TypeError)):
        spec.sql = "x"  # type: ignore[misc]


def test_every_known_kind_builds_a_listing_spec() -> None:
    # Smoke: each declared kind is handled (no fall-through error) when
    # given the minimum viable config.
    minimal: dict[str, dict[str, Any]] = {
        "file_upload": {"path": "/d/x.csv"},
        "parquet_glob": {"pattern": "/d/*.parquet"},
        "http": {"url": "https://h/d.csv"},
        "s3": {"url": "s3://b/k.csv"},
        "postgres": {"host": "h", "db": "d", "user": "u"},
        "mysql": {"host": "h", "db": "d", "user": "u"},
        "sqlite": {"path": "/db.sqlite"},
    }
    assert set(minimal) == set(INGEST_SOURCE_KINDS)
    for kind, config in minimal.items():
        assert isinstance(build_table_listing_spec(kind, config), ReaderSpec)
