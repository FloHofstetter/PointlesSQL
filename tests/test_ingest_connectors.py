"""per-kind connector reader-spec shape.

Pure unit tests against the builder functions in
:mod:`pointlessql.services.ingest.connectors`.  They never open a
DuckDB connection — the shape of the emitted SQL + extension set is
the contract this layer owes the probe / pull modules.
"""

from __future__ import annotations

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest.connectors import (
    build_reader_spec,
    build_table_listing_spec,
    quote_sql_identifier,
    quote_sql_string,
)


def test_file_upload_reader_uses_path_extension() -> None:
    """CSV / Parquet / JSON paths pick the right DuckDB reader."""
    csv_spec = build_reader_spec("file_upload", {"path": "/tmp/x.csv"})
    assert "read_csv_auto" in csv_spec.sql
    assert csv_spec.install == ()
    parquet_spec = build_reader_spec("file_upload", {"path": "/tmp/x.parquet"})
    assert "read_parquet" in parquet_spec.sql
    json_spec = build_reader_spec("file_upload", {"path": "/tmp/x.json"})
    assert "read_json_auto" in json_spec.sql


def test_parquet_glob_uses_read_parquet() -> None:
    """Parquet-glob spec wraps the pattern as a DuckDB string literal."""
    spec = build_reader_spec("parquet_glob", {"pattern": "/data/*.parquet"})
    assert "read_parquet" in spec.sql
    assert "/data/*.parquet" in spec.sql


def test_s3_reader_requires_httpfs() -> None:
    """S3 spec installs ``httpfs`` and emits the right reader."""
    spec = build_reader_spec("s3", {"url": "s3://my-bucket/orders.parquet"})
    assert "read_parquet" in spec.sql
    assert spec.install == ("httpfs",)


def test_http_reader_requires_httpfs() -> None:
    """HTTP CSV spec installs ``httpfs`` + picks ``read_csv_auto``."""
    spec = build_reader_spec("http", {"url": "https://example.com/data.csv"})
    assert "read_csv_auto" in spec.sql
    assert spec.install == ("httpfs",)


def test_postgres_reader_emits_postgres_scan() -> None:
    """Postgres spec embeds host/db/user, requires the ``postgres`` ext."""
    spec = build_reader_spec(
        "postgres",
        {"host": "db.internal", "port": 5432, "db": "orders", "user": "alice"},
        {"password": "s3cr3t"},
        source_table="public.orders",
    )
    assert "postgres_scan" in spec.sql
    assert "host=db.internal" in spec.sql
    assert "user=alice" in spec.sql
    assert spec.install == ("postgres",)


def test_mysql_reader_emits_mysql_scan() -> None:
    """MySQL spec emits ``mysql_scan(...)`` and installs ``mysql``."""
    spec = build_reader_spec(
        "mysql",
        {"host": "db", "port": 3306, "db": "shop", "user": "alice"},
        {"password": "pw"},
        source_table="shop.orders",
    )
    assert "mysql_scan" in spec.sql
    assert spec.install == ("mysql",)


def test_sqlite_reader_emits_sqlite_scan() -> None:
    """SQLite spec embeds the file path + the bare table name."""
    spec = build_reader_spec(
        "sqlite",
        {"path": "/tmp/test.db"},
        source_table="users",
    )
    assert "sqlite_scan" in spec.sql
    assert "/tmp/test.db" in spec.sql
    assert "users" in spec.sql
    assert spec.install == ("sqlite",)


def test_unknown_kind_raises() -> None:
    """An unknown kind is rejected up-front before any DuckDB call."""
    with pytest.raises(ValidationError, match="Unknown ingest source kind"):
        build_reader_spec("snowflake", {"account": "x"})


def test_file_kinds_short_circuit_table_listing() -> None:
    """File / S3 / HTTP / parquet_glob listings carry single_table_name."""
    for kind, cfg in (
        ("file_upload", {"path": "/tmp/x.csv"}),
        ("parquet_glob", {"pattern": "/data/*.parquet"}),
        ("http", {"url": "https://example.com/x.csv"}),
        ("s3", {"url": "s3://b/x.parquet"}),
    ):
        spec = build_table_listing_spec(kind, cfg)
        assert spec.single_table_name is not None, kind


def test_sql_listing_specs_use_information_schema() -> None:
    """Postgres / MySQL listings hit information_schema, SQLite hits master."""
    pg = build_table_listing_spec(
        "postgres",
        {"host": "h", "db": "d", "user": "u"},
        {"password": "p"},
    )
    assert "information_schema.tables" in pg.sql
    mysql = build_table_listing_spec(
        "mysql",
        {"host": "h", "db": "d", "user": "u"},
        {"password": "p"},
    )
    assert "information_schema.tables" in mysql.sql
    sqlite = build_table_listing_spec("sqlite", {"path": "/tmp/x.db"})
    assert "sqlite_master" in sqlite.sql


def test_postgres_requires_source_table_when_reading() -> None:
    """Postgres reader fails fast if no source_table was provided."""
    with pytest.raises(ValidationError, match="source_table"):
        build_reader_spec(
            "postgres",
            {"host": "h", "db": "d", "user": "u"},
            {"password": "p"},
            source_table=None,
        )


# -- required-field validation -----------------------------------------------


@pytest.mark.parametrize(
    ("kind", "config", "field"),
    [
        ("file_upload", {}, "path"),
        ("file_upload", {"path": "   "}, "path"),
        ("parquet_glob", {}, "pattern"),
        ("parquet_glob", {"pattern": ""}, "pattern"),
        ("http", {}, "url"),
        ("s3", {}, "url"),
    ],
)
def test_blank_required_field_rejected(kind: str, config: dict[str, object], field: str) -> None:
    """A missing/blank required config field raises ValidationError naming it."""
    with pytest.raises(ValidationError, match=field):
        build_reader_spec(kind, config)


def test_postgres_missing_host_db_user_rejected() -> None:
    """Postgres needs host/db/user; blank config is rejected (before secrets)."""
    with pytest.raises(ValidationError, match="host"):
        build_reader_spec("postgres", {}, {}, source_table="public.orders")


def test_source_table_with_too_many_parts_rejected() -> None:
    """A three-part source_table (``a.b.c``) is rejected — only schema.table/table."""
    with pytest.raises(ValidationError, match="schema.table"):
        build_reader_spec(
            "postgres",
            {"host": "h", "db": "d", "user": "u"},
            {"password": "p"},
            source_table="cat.schema.table",
        )


# -- SQL quoting helpers (injection-safety seam) -----------------------------


def test_quote_sql_string_doubles_embedded_quotes() -> None:
    assert quote_sql_string("plain") == "'plain'"
    assert quote_sql_string("foo'bar") == "'foo''bar'"
    # Consecutive quotes each get doubled.
    assert quote_sql_string("a''b") == "'a''''b'"
    assert quote_sql_string("") == "''"


def test_quote_sql_identifier_doubles_embedded_quotes() -> None:
    assert quote_sql_identifier("col") == '"col"'
    assert quote_sql_identifier('we"ird') == '"we""ird"'
    assert quote_sql_identifier('"') == '""""'
