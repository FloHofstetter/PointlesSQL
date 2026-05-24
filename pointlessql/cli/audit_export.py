r"""Verifiable audit-log export (Phase 75.1).

Ports the shoreguard-fresh ``cli_audit.py`` tamper-evidence pattern
(sha256 sidecar + manifest) to PointlesSQL.  Two surfaces:

* :func:`export_audit_to_files` — pure-function exporter used by
  both the CLI subcommand and the
  ``GET /admin/audit/export.tar.gz`` web endpoint.
* :func:`cli_entrypoint` — Typer subcommand entry-point invoked
  by ``pointlessql audit-export …``.

The exporter writes three mode-0600 files:

* ``<out>`` — data (JSON array or CSV).
* ``<out>.sha256`` — ``sha256sum``-compatible
  ``<hex>  <basename>\n``.
* ``<out>.manifest.json`` — ``{export_ts, filters, entry_count,
  tool_version, schema_version}``.

Compliance buyers verify the export by running
``sha256sum -c <out>.sha256`` against the data file and matching
the contained hash against ``<out>.manifest.json``'s recorded
``entry_count`` + filter set.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import pointlessql
from pointlessql.models.audit._log import AuditLog

logger = logging.getLogger(__name__)


_MANIFEST_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class ExportFilters:
    """Filter set captured in the manifest.

    Attributes:
        since: Cutoff timestamp (inclusive) or ``None`` for unbounded.
        until: End timestamp (exclusive) or ``None`` for now.
        action: Optional exact-match action filter.
        actor: Optional substring filter on ``user_email``.
        target: Optional substring filter on ``target``.
    """

    since: datetime.datetime | None
    until: datetime.datetime | None
    action: str | None
    actor: str | None
    target: str | None

    def to_manifest_dict(self) -> dict[str, str | None]:
        """Render for inclusion in the manifest JSON.

        Returns:
            A flat dict of string-or-null values suitable for
            JSON serialisation.
        """
        return {
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
        }


def serialise_rows(
    factory: sessionmaker[Any],
    filters: ExportFilters,
) -> list[dict[str, Any]]:
    """Run the filtered audit_log query and return one dict per row.

    Args:
        factory: SQLAlchemy sessionmaker.
        filters: :class:`ExportFilters` to apply.

    Returns:
        A list of audit_log row dicts in newest-first order.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if filters.since is not None:
        stmt = stmt.where(AuditLog.created_at >= filters.since)
    if filters.until is not None:
        stmt = stmt.where(AuditLog.created_at < filters.until)
    if filters.action:
        stmt = stmt.where(AuditLog.action == filters.action)
    if filters.actor:
        stmt = stmt.where(AuditLog.user_email.ilike(f"%{filters.actor}%"))
    if filters.target:
        stmt = stmt.where(AuditLog.target.ilike(f"%{filters.target}%"))
    with factory() as session:
        rows = list(session.scalars(stmt).all())
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "user_id": r.user_id,
            "user_email": r.user_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "target": r.target,
            "client_ip": r.client_ip or "",
            "detail": r.detail or "",
        }
        for r in rows
    ]


def encode_payload(
    rows: list[dict[str, Any]],
    *,
    fmt: Literal["json", "csv"],
    exported_at: datetime.datetime,
) -> bytes:
    """Encode *rows* as JSON or CSV bytes.

    Args:
        rows: Output of :func:`serialise_rows`.
        fmt: ``'json'`` or ``'csv'``.
        exported_at: Timestamp embedded in the JSON wrapper.

    Returns:
        UTF-8 encoded payload bytes.
    """
    if fmt == "json":
        body = json.dumps(
            {"exported_at": exported_at.isoformat(), "entries": rows},
            indent=2,
            sort_keys=True,
        )
        return body.encode("utf-8")
    buffer = io.StringIO()
    fieldnames = [
        "id",
        "created_at",
        "user_id",
        "user_email",
        "actor_role",
        "action",
        "target",
        "client_ip",
        "detail",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buffer.getvalue().encode("utf-8")


def write_sidecars(
    data_path: Path,
    payload: bytes,
    *,
    fmt: Literal["json", "csv"],
    filters: ExportFilters,
    entry_count: int,
    exported_at: datetime.datetime,
) -> tuple[Path, Path]:
    """Write the data file + ``.sha256`` + ``.manifest.json`` sidecars.

    All three files land at mode ``0o600`` so the cleartext audit
    rows are owner-readable only — matches the shoreguard-fresh
    pattern.

    Args:
        data_path: Where the payload goes.  Sidecars land beside
            it (``<data_path>.sha256`` + ``<data_path>.manifest.json``).
        payload: Bytes from :func:`encode_payload`.
        fmt: ``'json'`` or ``'csv'`` (recorded in the manifest).
        filters: Recorded in the manifest.
        entry_count: Number of rows exported (recorded in the
            manifest).
        exported_at: Timestamp recorded in the manifest.

    Returns:
        ``(sha256_path, manifest_path)`` so the caller can stream
        them (e.g. into a .tar.gz bundle).
    """
    data_path.write_bytes(payload)
    os.chmod(data_path, 0o600)

    sha = hashlib.sha256(payload).hexdigest()
    sha_path = data_path.with_name(data_path.name + ".sha256")
    sha_line = f"{sha}  {data_path.name}\n"
    sha_path.write_text(sha_line, encoding="ascii")
    os.chmod(sha_path, 0o600)

    manifest_path = data_path.with_name(data_path.name + ".manifest.json")
    manifest = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "tool_version": pointlessql.__version__,
        "exported_at": exported_at.isoformat(),
        "fmt": fmt,
        "filters": filters.to_manifest_dict(),
        "entry_count": entry_count,
        "data_sha256": sha,
        "data_filename": data_path.name,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.chmod(manifest_path, 0o600)
    return sha_path, manifest_path


def export_audit_to_files(
    factory: sessionmaker[Any],
    *,
    out: Path,
    fmt: Literal["json", "csv"] = "json",
    filters: ExportFilters,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """End-to-end exporter: query + encode + write sidecars.

    Args:
        factory: SQLAlchemy sessionmaker.
        out: Path the data file lands at.  Sidecars go next to it.
        fmt: ``'json'`` or ``'csv'``.
        filters: :class:`ExportFilters` to apply.
        now: Wall-clock override for tests.

    Returns:
        ``{"data_path", "sha256_path", "manifest_path",
        "entry_count", "sha256", "exported_at"}``.
    """
    exported_at = now or datetime.datetime.now(datetime.UTC)
    rows = serialise_rows(factory, filters)
    payload = encode_payload(rows, fmt=fmt, exported_at=exported_at)
    out.parent.mkdir(parents=True, exist_ok=True)
    sha_path, manifest_path = write_sidecars(
        out,
        payload,
        fmt=fmt,
        filters=filters,
        entry_count=len(rows),
        exported_at=exported_at,
    )
    sha = hashlib.sha256(payload).hexdigest()
    return {
        "data_path": str(out),
        "sha256_path": str(sha_path),
        "manifest_path": str(manifest_path),
        "entry_count": len(rows),
        "sha256": sha,
        "exported_at": exported_at.isoformat(),
    }


def cli_entrypoint(
    *,
    out: Path,
    fmt: Literal["json", "csv"],
    since: str | None,
    until: str | None,
    action: str | None,
    actor: str | None,
    target: str | None,
    db_url: str | None,
) -> int:
    """Typer-callable entry point.

    Args:
        out: Destination path for the data file.
        fmt: ``'json'`` or ``'csv'``.
        since: ISO-8601 cutoff (inclusive) or ``None``.
        until: ISO-8601 end (exclusive) or ``None``.
        action: Optional action filter.
        actor: Optional substring filter on user_email.
        target: Optional substring filter on target.
        db_url: SQLAlchemy URL override; ``None`` falls back to
            :class:`Settings`'s ``db.url``.

    Returns:
        Process exit code (``0`` on success, ``2`` on error).
    """
    from pointlessql.config import get_settings  # noqa: PLC0415
    from pointlessql.db import init_db  # noqa: PLC0415

    settings = get_settings()
    url = db_url or settings.db.url
    init_db(url)
    from pointlessql.db import get_session_factory  # noqa: PLC0415

    factory = get_session_factory()
    filters = ExportFilters(
        since=_parse_dt(since),
        until=_parse_dt(until),
        action=action,
        actor=actor,
        target=target,
    )
    result = export_audit_to_files(
        factory,
        out=out,
        fmt=fmt,
        filters=filters,
    )
    print(
        f"exported {result['entry_count']} row(s) to {result['data_path']}\n"
        f"  sha256: {result['sha256_path']}\n"
        f"  manifest: {result['manifest_path']}"
    )
    return 0


def _parse_dt(value: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 datetime string to UTC-aware datetime.

    Args:
        value: ISO-8601 string or ``None``.

    Returns:
        UTC-aware :class:`datetime.datetime` or ``None``.
    """
    if value is None:
        return None
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed
