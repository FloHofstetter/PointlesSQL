"""Restore a metadata-DB dump produced by :mod:`pointlessql.services.backup`.

Restore is a guarded operation: it verifies the payload hash, refuses a
dump taken on a schema newer than the running code, restores the payload
into the target DB, runs ``alembic upgrade head`` to bring an older dump
forward, and finally re-counts rows to compare against the manifest.

A ``dry_run`` restores into a throwaway location and reports what *would*
happen without touching the live target — the safe first step of any
recovery.  The function is operator-invoked (via the backup CLI), not part
of any request path.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

import pointlessql
from pointlessql.services.backup._dump import (
    _libpq_url,
    _sqlite_path,
    _table_rowcounts,
    dialect_of,
)
from pointlessql.services.backup._manifest import (
    BackupError,
    BackupManifest,
    validate_restorable,
    verify_payload,
)

logger = logging.getLogger(__name__)


def _alembic_dir() -> str:
    """Return the path to the embedded Alembic directory."""
    return str(Path(pointlessql.__file__).resolve().parent / "alembic")


def known_revisions() -> set[str]:
    """Return every Alembic revision id the running code knows about."""
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", _alembic_dir())
    script = ScriptDirectory.from_config(cfg)
    return {rev.revision for rev in script.walk_revisions()}


@dataclass
class RestoreReport:
    """Outcome of a restore (or dry-run).

    Attributes:
        dry_run: Whether the restore was applied to the live target.
        target_url: The DB URL restored into (the throwaway path for a
            dry-run).
        alembic_revision_after: The DB revision after ``upgrade head``.
        rowcount_mismatches: ``{table: (manifest_count, restored_count)}``
            for tables whose counts diverged (empty when consistent).
        warnings: Non-fatal notes accumulated during the restore.
    """

    dry_run: bool
    target_url: str
    alembic_revision_after: str | None = None
    rowcount_mismatches: dict[str, tuple[int, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _restore_sqlite(payload: bytes, target_path: str) -> None:
    """Overwrite the SQLite file at *target_path* with *payload*."""
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_bytes(payload)


def _restore_postgres(payload: bytes, target_url: str) -> None:
    """Restore a ``pg_dump`` custom archive into the target database."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".dump")
    os.close(tmp_fd)
    try:
        Path(tmp_path).write_bytes(payload)
        try:
            subprocess.run(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--dbname",
                    _libpq_url(target_url),
                    tmp_path,
                ],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise BackupError("pg_restore not found on PATH; install postgresql-client") from exc
        except subprocess.CalledProcessError as exc:
            raise BackupError(
                f"pg_restore failed: {exc.stderr.decode('utf-8', 'replace')[:500]}"
            ) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _upgrade_head(url: str) -> str | None:
    """Run ``alembic upgrade head`` against *url* and return the new revision."""
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", _alembic_dir())
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    script = ScriptDirectory.from_config(cfg)
    return script.get_current_head()


def restore_db(
    payload: bytes,
    manifest: BackupManifest,
    target_url: str,
    *,
    dry_run: bool = False,
    validate_schema: bool = True,
) -> RestoreReport:
    """Restore *payload* into *target_url*, guarded by *manifest*.

    Args:
        payload: The dump bytes (as returned by ``dump_db``).
        manifest: The dump's manifest (hash + revision + row counts).
        target_url: The SQLAlchemy URL to restore into.
        dry_run: When ``True``, restore into a throwaway DB and report
            without touching the live target.
        validate_schema: When ``True`` (default), refuse a dump whose
            revision the running code does not know.

    Returns:
        A :class:`RestoreReport`.

    Raises:
        BackupError: On hash mismatch, an unrestorable (too-new) dump, or
            a cross-dialect restore.
    """
    verify_payload(manifest, payload)
    if validate_schema:
        validate_restorable(manifest, known_revisions())

    target_dialect = dialect_of(target_url)
    if target_dialect != manifest.dialect:
        raise BackupError(
            f"cross-dialect restore not supported: dump is {manifest.dialect}, "
            f"target is {target_dialect}"
        )

    report = RestoreReport(dry_run=dry_run, target_url=target_url)

    if target_dialect == "sqlite":
        effective_url = target_url
        if dry_run:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
            os.close(tmp_fd)
            effective_url = f"sqlite:///{tmp_path}"
        try:
            _restore_sqlite(payload, _sqlite_path(effective_url))
            report.alembic_revision_after = _upgrade_head(effective_url)
            _check_rowcounts(effective_url, manifest, report)
        finally:
            if dry_run:
                Path(_sqlite_path(effective_url)).unlink(missing_ok=True)
        report.target_url = effective_url
        return report

    # Postgres: a dry-run cannot safely apply to a throwaway DB without
    # createdb privileges, so it validates + reports intent only.
    if dry_run:
        report.warnings.append(
            "postgres dry-run validated the manifest + payload but did not apply pg_restore "
            "(would need a throwaway database); run without --dry-run against a scratch DB to apply"
        )
        return report
    _restore_postgres(payload, target_url)
    report.alembic_revision_after = _upgrade_head(target_url)
    _check_rowcounts(target_url, manifest, report)
    return report


def _check_rowcounts(url: str, manifest: BackupManifest, report: RestoreReport) -> None:
    """Compare restored row counts against the manifest and record drift."""
    restored = _table_rowcounts(url)
    for table, expected in manifest.rowcounts.items():
        actual = restored.get(table)
        if actual is None:
            report.warnings.append(f"table {table!r} present in manifest but not after restore")
            continue
        if actual != expected:
            report.rowcount_mismatches[table] = (expected, actual)
