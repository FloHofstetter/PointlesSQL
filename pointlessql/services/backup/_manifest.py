"""Backup manifest — the verifiable sidecar that travels with a dump.

A manifest records everything needed to (a) verify a dump's integrity and
(b) decide whether the running code can safely restore it: the Alembic
revision the dump was taken at, the table row counts, the payload SHA-256,
the source dialect, and the timestamp.  Restore refuses a dump whose
revision the current code does not know — i.e. a backup taken on a *newer*
schema than the code being restored onto — because replaying it would land
the metadata DB in a state the code cannot migrate forward.

This mirrors the tamper-evidence shape of the audit export (a data payload
plus a hash sidecar plus a JSON manifest) so operators verify a backup the
same way they verify an export.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

_SCHEMA_VERSION = "1"


class BackupError(RuntimeError):
    """Raised when a backup cannot be produced, read, or safely restored."""


@dataclass(frozen=True)
class BackupManifest:
    """Integrity + provenance metadata for one metadata-DB dump.

    Attributes:
        schema_version: Manifest format version (currently ``"1"``).
        dialect: Source backend (``sqlite`` / ``postgresql``).
        alembic_revision: The dump's Alembic head revision, or ``None``
            if the source had no ``alembic_version`` row.
        dumped_at: ISO-8601 UTC timestamp the dump was taken.
        payload_sha256: SHA-256 of the dump payload bytes.
        rowcounts: Per-table row counts captured at dump time, used as a
            post-restore sanity check.
    """

    schema_version: str
    dialect: str
    alembic_revision: str | None
    dumped_at: str
    payload_sha256: str
    rowcounts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        """Return the manifest as a plain JSON-serialisable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BackupManifest:
        """Reconstruct a manifest from its dict form.

        Args:
            data: The parsed manifest JSON.

        Returns:
            The reconstructed :class:`BackupManifest`.

        Raises:
            BackupError: If a required field is missing.
        """
        try:
            return cls(
                schema_version=str(data["schema_version"]),
                dialect=str(data["dialect"]),
                alembic_revision=(
                    None if data.get("alembic_revision") is None else str(data["alembic_revision"])
                ),
                dumped_at=str(data["dumped_at"]),
                payload_sha256=str(data["payload_sha256"]),
                rowcounts=dict(data["rowcounts"]),  # type: ignore[arg-type]
            )
        except KeyError as exc:  # pragma: no cover - defensive
            raise BackupError(f"manifest missing required field: {exc}") from exc


def compute_sha256(payload: bytes) -> str:
    """Return the hex SHA-256 of *payload*."""
    return hashlib.sha256(payload).hexdigest()


def build_manifest(
    *,
    dialect: str,
    alembic_revision: str | None,
    dumped_at: str,
    payload: bytes,
    rowcounts: dict[str, int],
) -> BackupManifest:
    """Assemble a manifest for a freshly-produced dump payload."""
    return BackupManifest(
        schema_version=_SCHEMA_VERSION,
        dialect=dialect,
        alembic_revision=alembic_revision,
        dumped_at=dumped_at,
        payload_sha256=compute_sha256(payload),
        rowcounts=rowcounts,
    )


def write_manifest(manifest: BackupManifest, path: Path) -> None:
    """Write *manifest* to *path* as pretty-printed JSON (mode 0600)."""
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def read_manifest(path: Path) -> BackupManifest:
    """Read and parse a manifest JSON sidecar from *path*."""
    return BackupManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def verify_payload(manifest: BackupManifest, payload: bytes) -> None:
    """Raise :class:`BackupError` if *payload* does not match the manifest hash."""
    actual = compute_sha256(payload)
    if actual != manifest.payload_sha256:
        raise BackupError(
            f"backup payload hash mismatch: manifest={manifest.payload_sha256} actual={actual}"
        )


def validate_restorable(manifest: BackupManifest, known_revisions: set[str]) -> None:
    """Raise if the running code cannot safely restore this dump.

    A dump is restorable when its Alembic revision is one the current code
    knows about (present in the migration history): an older revision is
    fine — restore then ``upgrade head`` brings it forward — but a revision
    the code has never seen means the backup is from a *newer* schema and
    must not be force-fed into older code.

    Args:
        manifest: The dump's manifest.
        known_revisions: Every revision id in the code's migration history.

    Raises:
        BackupError: If the dump's revision is unknown to the current code.
    """
    revision = manifest.alembic_revision
    if revision is None:
        return
    if revision not in known_revisions:
        raise BackupError(
            f"backup was taken at Alembic revision {revision!r}, which this code does not "
            "know — it is newer than the running schema. Upgrade the code before restoring."
        )
