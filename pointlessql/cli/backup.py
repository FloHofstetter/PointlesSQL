"""Backup / restore CLI for the PointlesSQL metadata DB.

A standalone Typer app — ``python -m pointlessql.cli.backup backup …`` /
``… restore …`` — wrapping :mod:`pointlessql.services.backup`.  Kept
self-contained (its own ``app``) so it can run as a recovery tool even when
the full web app cannot start; wiring it into the main admin CLI is a
follow-up.

Examples:
    python -m pointlessql.cli.backup backup --out /backups/pql.dump
    python -m pointlessql.cli.backup restore --from /backups/pql.dump --dry-run
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import typer

from pointlessql.config import get_settings
from pointlessql.services.backup import (
    BackupError,
    dump_db,
    read_manifest,
    restore_db,
    write_manifest,
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="Backup and restore the PointlesSQL metadata DB.")


def _manifest_path(payload_path: Path) -> Path:
    """Return the sidecar manifest path for a payload path."""
    return payload_path.with_suffix(payload_path.suffix + ".manifest.json")


@app.command("backup")
def backup(
    out: Path = typer.Option(..., "--out", help="Destination path for the backup payload."),
    db_url: str | None = typer.Option(
        None, "--db-url", help="Source DB URL; defaults to the configured metadata DB."
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite an existing payload."),
) -> None:
    """Dump the metadata DB to *out* plus an ``<out>.manifest.json`` sidecar."""
    url = db_url or get_settings().db.url
    if out.exists() and not overwrite:
        typer.echo(f"refusing to overwrite existing {out} (pass --overwrite)", err=True)
        raise typer.Exit(code=2)
    dumped_at = datetime.datetime.now(datetime.UTC).isoformat()
    try:
        payload, manifest = dump_db(url, dumped_at=dumped_at)
    except BackupError as exc:
        typer.echo(f"backup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    out.chmod(0o600)
    write_manifest(manifest, _manifest_path(out))
    typer.echo(
        f"backup OK: {out} ({len(payload)} bytes), revision={manifest.alembic_revision}, "
        f"sha256={manifest.payload_sha256[:16]}…, tables={len(manifest.rowcounts)}"
    )


@app.command("restore")
def restore(
    from_path: Path = typer.Option(..., "--from", help="Backup payload to restore."),
    to_db: str | None = typer.Option(
        None, "--to-db", help="Target DB URL; defaults to the configured metadata DB."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate + report without applying."),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Skip the schema-compat (too-new-dump) guard."
    ),
) -> None:
    """Restore a backup payload into the target DB (guarded by its manifest)."""
    target = to_db or get_settings().db.url
    manifest_path = _manifest_path(from_path)
    if not manifest_path.exists():
        typer.echo(f"manifest sidecar not found at {manifest_path}", err=True)
        raise typer.Exit(code=2)
    payload = from_path.read_bytes()
    manifest = read_manifest(manifest_path)
    try:
        report = restore_db(
            payload,
            manifest,
            target,
            dry_run=dry_run,
            validate_schema=not skip_validation,
        )
    except BackupError as exc:
        typer.echo(f"restore refused: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"restore {'(dry-run) ' if dry_run else ''}OK: target={report.target_url}, "
        f"revision_after={report.alembic_revision_after}"
    )
    for warning in report.warnings:
        typer.echo(f"  warning: {warning}", err=True)
    if report.rowcount_mismatches:
        typer.echo("  row-count mismatches (manifest -> restored):", err=True)
        for table, (expected, actual) in sorted(report.rowcount_mismatches.items()):
            typer.echo(f"    {table}: {expected} -> {actual}", err=True)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    app()
