# pyright: reportUnusedFunction=false
# These are package-internal helpers for the autoload orchestrator in
# this package's __init__; they are 'unused' only within this sub-module.
"""Source-file enumeration, format resolution, and DuckDB read.

Internal helpers for :func:`pointlessql.pql.autoload`.
"""

from __future__ import annotations

import glob
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    pass


from pointlessql.exceptions import (
    ValidationError,
)
from pointlessql.pql._types import (
    ArrowTable,
    DuckdbCursor,
)

AutoloadFormat = Literal["auto", "parquet", "csv", "json"]

_FORMAT_BY_EXTENSION: dict[str, AutoloadFormat] = {
    ".parquet": "parquet",
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
}

_DUCKDB_READER_BY_FORMAT: dict[AutoloadFormat, str] = {
    "parquet": "read_parquet",
    "csv": "read_csv_auto",
    "json": "read_json_auto",
}

logger = logging.getLogger(__name__)


def _list_source_files(source_path: str | Path, file_format: AutoloadFormat) -> list[str]:
    """List files under *source_path* matching the requested format.

    A path containing glob characters is treated as a glob; otherwise
    we walk the directory tree and keep files whose extension maps to
    a supported format (or to *file_format* when it is not ``"auto"``).
    Ordering is deterministic (sorted) so the autoload-then-checkpoint
    sequence is reproducible across runs.

    Args:
        source_path: Local filesystem path or glob.
        file_format: ``"auto"`` or an explicit format.

    Returns:
        List of absolute file paths in sorted order.
    """
    raw = str(source_path)
    if any(ch in raw for ch in ("*", "?", "[")):
        candidates = sorted(p for p in glob.glob(raw, recursive=True) if Path(p).is_file())
    else:
        root = Path(raw)
        if root.is_file():
            candidates = [str(root)]
        elif root.is_dir():
            candidates = sorted(str(p) for p in root.rglob("*") if p.is_file())
        else:
            candidates = []

    if file_format == "auto":
        return [p for p in candidates if Path(p).suffix.lower() in _FORMAT_BY_EXTENSION]

    target_ext = {ext for ext, fmt in _FORMAT_BY_EXTENSION.items() if fmt == file_format}
    return [p for p in candidates if Path(p).suffix.lower() in target_ext]


def _resolve_file_format(file_path: str, file_format: AutoloadFormat) -> AutoloadFormat:
    """Decide which DuckDB reader to use for *file_path*.

    Args:
        file_path: Absolute path of the source file.
        file_format: ``"auto"`` to derive from the extension, or an
            explicit override.

    Returns:
        One of ``"parquet"`` / ``"csv"`` / ``"json"``.

    Raises:
        ValidationError: When ``file_format`` is ``"auto"`` and the
            extension isn't in :data:`_FORMAT_BY_EXTENSION`.
    """
    if file_format != "auto":
        return file_format
    ext = Path(file_path).suffix.lower()
    inferred = _FORMAT_BY_EXTENSION.get(ext)
    if inferred is None:
        raise ValidationError(
            f"autoload could not infer file_format for {file_path!r} — "
            f"pass file_format='parquet'/'csv'/'json' explicitly"
        )
    return inferred


def _read_file_via_duckdb(file_path: str, file_format: AutoloadFormat) -> ArrowTable:
    """Read *file_path* through DuckDB and return a PyArrow Table.

    Args:
        file_path: Absolute path of the source file.
        file_format: One of the explicit formats.

    Returns:
        A PyArrow Table with DuckDB-inferred types.
    """
    import duckdb

    reader = _DUCKDB_READER_BY_FORMAT[file_format]
    conn = duckdb.connect()
    try:
        # The DuckDB readers accept positional path arguments and
        # tolerate arbitrary file system paths; the SQL injection
        # surface is bounded because file_path comes from a directory
        # walk we just did, not from user input.
        cursor = cast(DuckdbCursor, conn.execute(f"SELECT * FROM {reader}(?)", [file_path]))
        return cursor.fetch_arrow_table()
    finally:
        conn.close()
