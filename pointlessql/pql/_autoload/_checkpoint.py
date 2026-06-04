# pyright: reportUnusedFunction=false
# These are package-internal helpers for the autoload orchestrator in
# this package's __init__; they are 'unused' only within this sub-module.
"""File-level exactly-once SHA-256 checkpoint bookkeeping.

Internal helpers for :func:`pointlessql.pql.autoload`.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import AutoloadCheckpoint

logger = logging.getLogger(__name__)


def _sha256_file(file_path: str) -> str:
    """Return the SHA-256 hex digest of the file's bytes.

    Reads in 1-MB chunks so very large source files don't push the
    process into swap.

    Args:
        file_path: Absolute path of the file to hash.

    Returns:
        64-character lowercase hex digest.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _checkpoint_exists(session_factory: sessionmaker[Session], target: str, sha: str) -> bool:
    """Return whether ``(target, sha)`` is already recorded.

    Args:
        session_factory: SQLAlchemy session factory.
        target: UC ``"catalog.schema.table"`` string.
        sha: SHA-256 hex digest.

    Returns:
        ``True`` when the row exists.
    """
    with session_factory() as session:
        stmt = select(AutoloadCheckpoint.id).where(
            AutoloadCheckpoint.target_table == target,
            AutoloadCheckpoint.file_sha == sha,
        )
        return session.scalar(stmt) is not None


def _record_checkpoint(
    session_factory: sessionmaker[Session],
    *,
    source_path: str,
    file_sha: str,
    target_table: str,
    ingested_at: datetime.datetime,
    rows_ingested: int,
) -> None:
    """Insert one ``autoload_checkpoints`` row.

    Args:
        session_factory: SQLAlchemy session factory.
        source_path: Source file path.
        file_sha: SHA-256 hex digest of the file's bytes.
        target_table: UC ``"catalog.schema.table"`` string.
        ingested_at: UTC timestamp the autoload appended.
        rows_ingested: Row count delivered into the target.
    """
    with session_factory() as session:
        row = AutoloadCheckpoint(
            source_path=source_path,
            file_sha=file_sha,
            target_table=target_table,
            ingested_at=ingested_at,
            rows_ingested=rows_ingested,
        )
        session.add(row)
        session.commit()
