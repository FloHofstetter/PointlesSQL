"""Autoload checkpoints — file-level exactly-once for ingestion.

The ``pql.autoload`` primitive consults this table before reading
a Volume file and records a row after a successful append, so a
re-run over the same directory skips already-ingested files.

Identity is the ``(target_table, file_sha)`` tuple — a unique
constraint backs the cheap "have I done this?" probe.  The same
source file pulled into two different bronze tables (e.g. when
an operator A/B-tests a schema change) stays addressable because
the target_table participates in the key.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class AutoloadCheckpoint(Base):
    """One ``(target_table, file)`` ingestion record.

    The autoload primitive writes one row per file it appends
    into the target Delta table.  The SHA-256 covers the file
    bytes verbatim — file rename / move under the same Volume
    path is intentionally treated as the same content (you are
    just relabelling), while content edit produces a new SHA
    and re-ingests with audit columns referencing the new
    contents.

    Attributes:
        id: Surrogate primary key.  No semantic meaning — the
            unique constraint on ``(target_table, file_sha)``
            is the real identity.
        source_path: Volume-relative or filesystem path of the
            source file.  Stored for audit / control-room
            visibility, not for dedup (the SHA does that).
        file_sha: SHA-256 hex digest of the source file bytes.
        target_table: UC ``"catalog.schema.table"`` the row was
            appended into.
        ingested_at: UTC timestamp the autoload run committed.
        rows_ingested: Row count delivered into the target.
    """

    __tablename__ = "autoload_checkpoints"

    __table_args__ = (
        UniqueConstraint("target_table", "file_sha", name="uq_autoload_target_sha"),
        Index(
            "ix_autoload_checkpoints_target_path",
            "target_table",
            "source_path",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(512), nullable=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rows_ingested: Mapped[int] = mapped_column(Integer, nullable=False)
