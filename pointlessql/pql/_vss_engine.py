"""Thin DuckDB wrapper for the ``vss`` extension.

The ``vss`` extension ships with DuckDB ≥ 0.10 but is loaded lazily
via ``INSTALL vss; LOAD vss;``.  This module owns the once-per-
process load and exposes :func:`open_index` to open (or create) the
per-column ``.duckdb`` index files at the standard
``<storage_root>/<schema>/<table>/_vss/<column>.duckdb`` layout.

The schema inside each index file is fixed:

* ``embeddings(rowid BIGINT PRIMARY KEY, pk_json VARCHAR,
  source_text VARCHAR, vector FLOAT[dim])`` — one row per source-
  table row that carried a non-null text value.
* ``meta(key VARCHAR PRIMARY KEY, value VARCHAR)`` — opaque
  key/value store carrying the index's ``dim``, ``model``,
  ``embedder``, ``metric``, HNSW parameters, ``delta_version_indexed``,
  and the canonical ``column`` name.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import duckdb

__all__ = [
    "INDEX_TABLE_SQL_TEMPLATE",
    "META_TABLE_SQL",
    "load_vss_extension",
    "open_index",
    "read_meta",
    "write_meta",
]

logger = logging.getLogger(__name__)


META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key VARCHAR PRIMARY KEY,
    value VARCHAR
)
""".strip()


INDEX_TABLE_SQL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS embeddings (
    rowid BIGINT PRIMARY KEY,
    pk_json VARCHAR,
    source_text VARCHAR,
    vector FLOAT[{dim}]
)
""".strip()


_EXTENSION_LOAD_LOCK = threading.Lock()
_loaded_by_process_pid: int | None = None


def load_vss_extension(conn: duckdb.DuckDBPyConnection) -> None:
    """Ensure the ``vss`` extension is installed + loaded on ``conn``.

    DuckDB extensions are per-connection: each new connection must
    call ``LOAD vss``.  The install step runs once per process; the
    load step runs once per connection.

    Persistent (file-backed) HNSW indices require
    ``hnsw_enable_experimental_persistence = true`` — the flag is
    still marked experimental in duckdb-vss but the on-disk format
    is stable enough for our use-case (rebuilt on every
    ``pql.merge`` write).

    A ``duckdb.Error`` propagates from ``INSTALL`` / ``LOAD`` when the
    extension cannot be installed — e.g. sandboxed environments without
    internet access on the first install.

    Args:
        conn: DuckDB connection.
    """
    global _loaded_by_process_pid
    with _EXTENSION_LOAD_LOCK:
        pid = os.getpid()
        if _loaded_by_process_pid != pid:
            # ``INSTALL`` is a no-op when the extension is already on
            # disk; safe to call repeatedly per process.
            conn.execute("INSTALL vss")
            _loaded_by_process_pid = pid
    conn.execute("LOAD vss")
    conn.execute("SET hnsw_enable_experimental_persistence = true")


def open_index(
    path: str | Path,
    *,
    dim: int,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open (or create + bootstrap) the per-column index file at *path*.

    Args:
        path: Filesystem path to the ``.duckdb`` index file.
        dim: Embedding dimensionality.  Used only when bootstrapping
            a fresh file — ignored on subsequent opens.
        read_only: When ``True``, open the file read-only.  Search
            uses this so concurrent rebuilds + searches do not block
            each other.

    Returns:
        A live :class:`duckdb.DuckDBPyConnection` with the ``vss``
        extension loaded.
    """
    p = Path(path)
    if not read_only:
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(p), read_only=read_only)
    load_vss_extension(conn)
    if not read_only:
        conn.execute(META_TABLE_SQL)
        conn.execute(INDEX_TABLE_SQL_TEMPLATE.format(dim=dim))
    return conn


def read_meta(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Load the ``meta`` table into a plain dict.

    Args:
        conn: Connection opened via :func:`open_index`.

    Returns:
        Dict of meta key/value pairs.  Numeric strings are parsed
        back to ``int`` / ``float`` opportunistically; everything
        else stays as-is.
    """
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    out: dict[str, Any] = {}
    for key, value in rows:
        out[key] = _coerce(value)
    return out


def write_meta(conn: duckdb.DuckDBPyConnection, **values: Any) -> None:
    """Upsert one or more rows into the ``meta`` table.

    Args:
        conn: Connection opened via :func:`open_index` (must not be
            read-only).
        **values: Key-value pairs.  Non-string values are
            JSON-serialised so ``read_meta`` can round-trip them.
    """
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            stored: str = "" if value is None else str(value)
        else:
            stored = json.dumps(value, default=str)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [key, stored],
        )


def _coerce(value: str) -> Any:
    """Best-effort string→primitive coercion for ``meta`` reads."""
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value in {"True", "true"}:
        return True
    if value in {"False", "false"}:
        return False
    return value
