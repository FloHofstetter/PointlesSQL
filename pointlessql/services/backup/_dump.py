"""Dialect-aware dump of the PointlesSQL metadata DB.

Produces a single payload (bytes) plus a :class:`BackupManifest`.  SQLite
uses the online backup API (consistent even with WAL active — never a raw
file copy), Postgres shells out to ``pg_dump`` in the custom archive
format.  Either way the manifest captures the Alembic revision and per-table
row counts so a later restore can be validated.

Only the *own* metadata DB (sessions / preferences / audit / scheduler /
lineage rows) is dumped here — the Delta lakehouse layer is a separate
storage concern documented in the DR runbook, not part of this payload.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from pointlessql.services.backup._manifest import BackupError, BackupManifest, build_manifest

logger = logging.getLogger(__name__)


def dialect_of(url: str) -> str:
    """Return ``"sqlite"`` or ``"postgresql"`` for a SQLAlchemy URL.

    Raises:
        BackupError: For any other (unsupported) backend.
    """
    if url.startswith("sqlite"):
        return "sqlite"
    if url.startswith("postgresql") or url.startswith("postgres"):
        return "postgresql"
    raise BackupError(f"unsupported backend for backup: {url.split(':', 1)[0]}")


def _sqlite_path(url: str) -> str:
    """Extract the on-disk path from a ``sqlite:///path`` URL."""
    path = url.split("///", 1)[-1]
    if not path or path == ":memory:":
        raise BackupError("cannot back up an in-memory or path-less SQLite DB")
    return path


def _libpq_url(url: str) -> str:
    """Strip the SQLAlchemy driver suffix so ``pg_dump`` accepts the URL."""
    # postgresql+psycopg://… -> postgresql://…
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        return f"{scheme.split('+', 1)[0]}://{rest}"
    return url


def _dump_sqlite(url: str) -> bytes:
    """Return a consistent SQLite snapshot via the online backup API."""
    src_path = _sqlite_path(url)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    try:
        src = sqlite3.connect(src_path)
        try:
            dst = sqlite3.connect(tmp_path)
            try:
                with dst:
                    src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _dump_postgres(url: str) -> bytes:
    """Return a ``pg_dump`` custom-format archive of the database."""
    try:
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", _libpq_url(url)],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise BackupError("pg_dump not found on PATH; install postgresql-client") from exc
    except subprocess.CalledProcessError as exc:
        raise BackupError(f"pg_dump failed: {exc.stderr.decode('utf-8', 'replace')[:500]}") from exc
    return result.stdout


def _table_rowcounts(url: str) -> dict[str, int]:
    """Return a ``{table: count}`` map for every table in the DB."""
    engine = create_engine(url)
    counts: dict[str, int] = {}
    try:
        inspector = inspect(engine)
        with engine.connect() as conn:
            for table in sorted(inspector.get_table_names()):
                row = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()
                counts[table] = int(row or 0)
    finally:
        engine.dispose()
    return counts


def _current_revision(url: str) -> str | None:
    """Return the DB's current Alembic revision, or ``None`` if unstamped."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            try:
                row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:  # noqa: BLE001 — table may not exist on a fresh DB
                return None
            return None if row is None else str(row)
    finally:
        engine.dispose()


def dump_db(url: str, *, dumped_at: str) -> tuple[bytes, BackupManifest]:
    """Dump the metadata DB at *url* and return ``(payload, manifest)``.

    Args:
        url: The SQLAlchemy URL of the metadata DB to back up.
        dumped_at: ISO-8601 UTC timestamp to stamp into the manifest
            (passed in so the dump is deterministic and clock-free).

    Returns:
        A ``(payload_bytes, manifest)`` tuple.  Persist both — the payload
        as the backup archive and ``write_manifest`` for the sidecar.
    """
    dialect = dialect_of(url)
    payload = _dump_sqlite(url) if dialect == "sqlite" else _dump_postgres(url)
    rowcounts = _table_rowcounts(url)
    revision = _current_revision(url)
    manifest = build_manifest(
        dialect=dialect,
        alembic_revision=revision,
        dumped_at=dumped_at,
        payload=payload,
        rowcounts=rowcounts,
    )
    logger.info(
        "metadata DB dump complete: dialect=%s revision=%s tables=%d bytes=%d",
        dialect,
        revision,
        len(rowcounts),
        len(payload),
    )
    return payload, manifest
