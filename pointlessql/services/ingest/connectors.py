"""Per-kind DuckDB reader builders.

Each connector kind exposes two builder functions:

* :func:`build_reader_spec` — given ``(kind, config, secrets,
  source_table?)`` returns a :class:`ReaderSpec` whose ``sql`` selects
  rows from the external system through the appropriate DuckDB reader.
* :func:`build_table_listing_spec` — given ``(kind, config, secrets)``
  returns a :class:`ReaderSpec` whose ``sql`` lists the available
  tables on the source.  For file-based connectors that represent a
  single logical table this short-circuits to a one-row response so
  the UI table-picker stays uniform across kinds.

Both builders are pure functions — they never open a DuckDB
connection — so they unit-test cleanly.  Actual extension installation
+ query execution happens in :mod:`.probe` and :mod:`.pull`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.models.ingest import INGEST_SOURCE_KINDS


@dataclass(frozen=True, slots=True)
class ReaderSpec:
    """A self-contained DuckDB query plan for one read operation.

    Attributes:
        sql: The DuckDB SQL string ready for ``cursor.execute(sql)``.
        install: Tuple of DuckDB extension names that must be
            ``INSTALL``-ed + ``LOAD``-ed before ``sql`` runs.  Empty
            tuple when no extension is needed (file-based formats use
            built-in readers).
        single_table_name: When non-``None``, marks this spec as
            representing a single logical "table" — used by the
            table-listing path so file-based connectors can short-
            circuit to one row without hitting the source.
    """

    sql: str
    install: tuple[str, ...] = ()
    single_table_name: str | None = field(default=None)


def quote_sql_string(value: str) -> str:
    """Return ``value`` quoted as a DuckDB single-quoted string literal.

    Doubles every embedded single quote per the DuckDB / SQL standard.
    Used for connection-string fragments so passwords like ``foo'bar``
    don't break the surrounding query.

    Args:
        value: Raw string to embed.

    Returns:
        Single-quoted SQL literal.
    """
    return "'" + value.replace("'", "''") + "'"


def quote_sql_identifier(value: str) -> str:
    """Return ``value`` quoted as a DuckDB identifier (double-quoted).

    Args:
        value: Raw identifier (schema / table / column name).

    Returns:
        Double-quoted SQL identifier with internal quotes escaped.
    """
    return '"' + value.replace('"', '""') + '"'


def _validate_kind(kind: str) -> None:
    """Reject an unknown connector kind early.

    Args:
        kind: Caller-supplied kind string.

    Raises:
        ValidationError: When ``kind`` is not in
            :data:`pointlessql.models.ingest.INGEST_SOURCE_KINDS`.
    """
    if kind not in INGEST_SOURCE_KINDS:
        raise ValidationError(
            f"Unknown ingest source kind: {kind!r}. Expected one of {INGEST_SOURCE_KINDS}."
        )


def _file_reader_for_path(path: str) -> tuple[str, str | None]:
    """Pick the DuckDB reader function for a local-file or URL path.

    Looks at the file extension only; mismatched extensions are the
    caller's problem (DuckDB will fail loudly).

    Args:
        path: File path, URL, or glob pattern.

    Returns:
        ``(reader_function, single_table_basename_or_None)``.

    Raises:
        ValidationError: When the extension is not one of
            ``.csv`` / ``.parquet`` / ``.json`` / ``.jsonl`` /
            ``.ndjson``.
    """
    lower = path.lower()
    if lower.endswith(".parquet"):
        reader = "read_parquet"
    elif lower.endswith(".csv"):
        reader = "read_csv_auto"
    elif lower.endswith((".json", ".jsonl", ".ndjson")):
        reader = "read_json_auto"
    else:
        raise ValidationError(
            f"Cannot pick a DuckDB reader for path {path!r}. "
            "Expected .csv / .parquet / .json / .jsonl / .ndjson."
        )
    # Strip query string / glob wildcards for the friendly table name.
    base = PurePosixPath(path.split("?", 1)[0]).name
    return reader, base or None


def _build_file_upload_spec(config: dict[str, Any], source_table: str | None) -> ReaderSpec:
    """Build the reader for a server-side local file path."""
    del source_table  # file_upload always reads its single configured path
    path = str(config.get("path") or "").strip()
    if not path:
        raise ValidationError("file_upload source requires 'path' in config.")
    reader, base = _file_reader_for_path(path)
    return ReaderSpec(
        sql=f"SELECT * FROM {reader}({quote_sql_string(path)})",
        single_table_name=base,
    )


def _build_parquet_glob_spec(config: dict[str, Any], source_table: str | None) -> ReaderSpec:
    """Build the reader for a parquet glob pattern."""
    del source_table
    pattern = str(config.get("pattern") or "").strip()
    if not pattern:
        raise ValidationError("parquet_glob source requires 'pattern' in config.")
    return ReaderSpec(
        sql=f"SELECT * FROM read_parquet({quote_sql_string(pattern)})",
        single_table_name=PurePosixPath(pattern).name or "parquet_glob",
    )


def _build_http_spec(config: dict[str, Any], source_table: str | None) -> ReaderSpec:
    """Build the reader for an HTTP(S) URL.

    Uses DuckDB's ``httpfs`` extension.  Bearer / basic auth headers
    are not supported in v1 — ``httpfs`` configuration via DuckDB
    SETTINGS happens in :func:`pointlessql.services.ingest.probe`.
    """
    del source_table
    url = str(config.get("url") or "").strip()
    if not url:
        raise ValidationError("http source requires 'url' in config.")
    reader, base = _file_reader_for_path(url)
    return ReaderSpec(
        sql=f"SELECT * FROM {reader}({quote_sql_string(url)})",
        install=("httpfs",),
        single_table_name=base,
    )


def _build_s3_spec(config: dict[str, Any], source_table: str | None) -> ReaderSpec:
    """Build the reader for an S3 URL.

    Credentials live in ``secrets`` but DuckDB consumes them via SET
    statements wired in :mod:`.probe`.  This builder only emits the
    SELECT; the SET prelude is added by the caller.
    """
    del source_table
    url = str(config.get("url") or "").strip()
    if not url:
        raise ValidationError("s3 source requires 'url' in config.")
    reader, base = _file_reader_for_path(url)
    return ReaderSpec(
        sql=f"SELECT * FROM {reader}({quote_sql_string(url)})",
        install=("httpfs",),
        single_table_name=base,
    )


def _build_postgres_spec(
    config: dict[str, Any], secrets: dict[str, Any], source_table: str | None
) -> ReaderSpec:
    """Build the reader for a Postgres source table.

    Uses DuckDB's ``postgres_scanner`` extension (registered as
    ``postgres`` since DuckDB 0.10).
    """
    if not source_table:
        raise ValidationError("postgres source requires 'source_table' (schema.table).")
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or 5432)
    db = str(config.get("db") or "").strip()
    user = str(config.get("user") or "").strip()
    password = str(secrets.get("password") or "")
    if not host or not db or not user:
        raise ValidationError("postgres source requires 'host', 'db', and 'user' in config.")
    schema, table = _split_qualified_table(source_table, default_schema="public")
    conn_str = f"host={host} port={port} dbname={db} user={user} password={password}"
    return ReaderSpec(
        sql=(
            f"SELECT * FROM postgres_scan("
            f"{quote_sql_string(conn_str)}, "
            f"{quote_sql_string(schema)}, "
            f"{quote_sql_string(table)})"
        ),
        install=("postgres",),
    )


def _build_mysql_spec(
    config: dict[str, Any], secrets: dict[str, Any], source_table: str | None
) -> ReaderSpec:
    """Build the reader for a MySQL source table.

    Uses DuckDB's ``mysql_scanner`` extension (registered as
    ``mysql``).
    """
    if not source_table:
        raise ValidationError("mysql source requires 'source_table' (schema.table).")
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or 3306)
    db = str(config.get("db") or "").strip()
    user = str(config.get("user") or "").strip()
    password = str(secrets.get("password") or "")
    if not host or not db or not user:
        raise ValidationError("mysql source requires 'host', 'db', and 'user' in config.")
    schema, table = _split_qualified_table(source_table, default_schema=db)
    # mysql_scanner uses ATTACH-style connection strings under the
    # hood; the simplest reader path is the inline mysql_scan helper.
    conn_str = f"host={host} port={port} database={db} user={user} password={password}"
    return ReaderSpec(
        sql=(
            f"SELECT * FROM mysql_scan("
            f"{quote_sql_string(conn_str)}, "
            f"{quote_sql_string(schema)}, "
            f"{quote_sql_string(table)})"
        ),
        install=("mysql",),
    )


def _build_sqlite_spec(config: dict[str, Any], source_table: str | None) -> ReaderSpec:
    """Build the reader for a SQLite source table.

    Uses DuckDB's ``sqlite_scanner`` extension (registered as
    ``sqlite``).
    """
    if not source_table:
        raise ValidationError("sqlite source requires 'source_table' (table name).")
    path = str(config.get("path") or "").strip()
    if not path:
        raise ValidationError("sqlite source requires 'path' in config.")
    # sqlite_scan takes (db_path, table_name); SQLite has no schema
    # concept beyond the file itself, so we ignore any schema prefix.
    _, table = _split_qualified_table(source_table, default_schema="")
    return ReaderSpec(
        sql=(f"SELECT * FROM sqlite_scan({quote_sql_string(path)}, {quote_sql_string(table)})"),
        install=("sqlite",),
    )


def _split_qualified_table(qualified: str, *, default_schema: str) -> tuple[str, str]:
    """Split a ``schema.table`` (or bare ``table``) into its parts."""
    parts = qualified.split(".")
    if len(parts) == 1:
        return default_schema, parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValidationError(f"source_table must be 'schema.table' or 'table', got {qualified!r}.")


def build_reader_spec(
    kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
    source_table: str | None = None,
) -> ReaderSpec:
    """Return the DuckDB reader spec for a single read operation.

    Args:
        kind: One of :data:`pointlessql.models.ingest.INGEST_SOURCE_KINDS`.
        config: Non-secret connection parameters.
        secrets: Plaintext credentials (``None`` when the kind doesn't
            need any).
        source_table: For SQL connectors, the source-side table name
            in ``schema.table`` form (or bare ``table``).  Ignored for
            file-based connectors.

    Returns:
        A :class:`ReaderSpec` describing the SQL + required extensions.

    Raises:
        ValidationError: When *kind* is unknown or required keys are
            missing from *config* / *secrets*.
    """
    _validate_kind(kind)
    secrets_dict: dict[str, Any] = secrets or {}
    if kind == "file_upload":
        return _build_file_upload_spec(config, source_table)
    if kind == "parquet_glob":
        return _build_parquet_glob_spec(config, source_table)
    if kind == "http":
        return _build_http_spec(config, source_table)
    if kind == "s3":
        return _build_s3_spec(config, source_table)
    if kind == "postgres":
        return _build_postgres_spec(config, secrets_dict, source_table)
    if kind == "mysql":
        return _build_mysql_spec(config, secrets_dict, source_table)
    if kind == "sqlite":
        return _build_sqlite_spec(config, source_table)
    # _validate_kind already covered every kind; this is unreachable.
    raise ValidationError(f"Unknown ingest source kind: {kind!r}.")


def build_table_listing_spec(
    kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> ReaderSpec:
    """Return the DuckDB spec that lists available tables on the source.

    For file-based connectors (``file_upload``, ``http``, ``s3``,
    ``parquet_glob``) the source represents a single logical table.
    The returned spec carries ``single_table_name`` so the caller can
    short-circuit to a one-row response without hitting DuckDB.

    For SQL connectors the spec is a real query against the source's
    catalog (``information_schema.tables`` for Postgres/MySQL,
    ``sqlite_master`` for SQLite).

    Args:
        kind: Connector kind.
        config: Non-secret connection parameters.
        secrets: Plaintext credentials.

    Returns:
        A :class:`ReaderSpec` that either produces the listing query
        or short-circuits via ``single_table_name``.

    Raises:
        ValidationError: When *kind* is unknown or required keys are
            missing.
    """
    _validate_kind(kind)
    secrets_dict: dict[str, Any] = secrets or {}
    if kind in {"file_upload", "parquet_glob", "http", "s3"}:
        # Reuse the regular reader spec so we get the same
        # ``single_table_name`` derived from the path.
        spec = build_reader_spec(kind, config, secrets_dict, source_table=None)
        return ReaderSpec(
            sql="SELECT 1 WHERE 1=0",  # never executed
            install=spec.install,
            single_table_name=spec.single_table_name,
        )
    if kind == "postgres":
        host = str(config.get("host") or "").strip()
        port = int(config.get("port") or 5432)
        db = str(config.get("db") or "").strip()
        user = str(config.get("user") or "").strip()
        password = str(secrets_dict.get("password") or "")
        if not host or not db or not user:
            raise ValidationError("postgres source requires 'host', 'db', and 'user' in config.")
        conn_str = f"host={host} port={port} dbname={db} user={user} password={password}"
        # ATTACH the database, then query information_schema.
        return ReaderSpec(
            sql=(
                f"ATTACH {quote_sql_string(conn_str)} AS _pql_src "
                "(TYPE postgres, READ_ONLY); "
                "SELECT table_schema || '.' || table_name AS name "
                "FROM _pql_src.information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
                "ORDER BY 1; "
                "DETACH _pql_src;"
            ),
            install=("postgres",),
        )
    if kind == "mysql":
        host = str(config.get("host") or "").strip()
        port = int(config.get("port") or 3306)
        db = str(config.get("db") or "").strip()
        user = str(config.get("user") or "").strip()
        password = str(secrets_dict.get("password") or "")
        if not host or not db or not user:
            raise ValidationError("mysql source requires 'host', 'db', and 'user' in config.")
        conn_str = f"host={host} port={port} database={db} user={user} password={password}"
        return ReaderSpec(
            sql=(
                f"ATTACH {quote_sql_string(conn_str)} AS _pql_src "
                "(TYPE mysql, READ_ONLY); "
                "SELECT table_schema || '.' || table_name AS name "
                "FROM _pql_src.information_schema.tables "
                "WHERE table_schema NOT IN "
                "('mysql','information_schema','sys','performance_schema') "
                "ORDER BY 1; "
                "DETACH _pql_src;"
            ),
            install=("mysql",),
        )
    if kind == "sqlite":
        path = str(config.get("path") or "").strip()
        if not path:
            raise ValidationError("sqlite source requires 'path' in config.")
        return ReaderSpec(
            sql=(
                f"ATTACH {quote_sql_string(path)} AS _pql_src "
                "(TYPE sqlite, READ_ONLY); "
                "SELECT name FROM _pql_src.sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY 1; "
                "DETACH _pql_src;"
            ),
            install=("sqlite",),
        )
    raise ValidationError(f"Unknown ingest source kind: {kind!r}.")
