"""Backup / restore of the PointlesSQL metadata DB.

Re-export facade for the disaster-recovery toolkit: dump the own metadata
DB to a verifiable payload + manifest, restore it (guarded by a schema
check), and run post-restore consistency checks.  The lakehouse Delta layer
is a separate storage concern handled outside this package — see the DR
runbook in ``docs/admin/disaster-recovery.md``.
"""

from __future__ import annotations

from pointlessql.services.backup._consistency import ConsistencyReport, check_consistency
from pointlessql.services.backup._dump import dialect_of, dump_db
from pointlessql.services.backup._manifest import (
    BackupError,
    BackupManifest,
    build_manifest,
    compute_sha256,
    read_manifest,
    validate_restorable,
    verify_payload,
    write_manifest,
)
from pointlessql.services.backup._restore import RestoreReport, known_revisions, restore_db

__all__ = [
    "BackupError",
    "BackupManifest",
    "ConsistencyReport",
    "RestoreReport",
    "build_manifest",
    "check_consistency",
    "compute_sha256",
    "dialect_of",
    "dump_db",
    "known_revisions",
    "read_manifest",
    "restore_db",
    "validate_restorable",
    "verify_payload",
    "write_manifest",
]
