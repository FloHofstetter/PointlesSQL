"""Auto-loader processed-files registry for incremental ingest.

One row per ``(ingest_source, mapping_index, file_path)`` triple that
the auto-loader pull path has already appended into the mapping's
Delta target.  The registry is what turns a file-based pull from a
full re-read into an incremental discover-then-append: discovery
globs the source pattern and subtracts the paths recorded here.

Rows are written *after* a file's append succeeded, which gives the
loader at-least-once semantics — a crash between the Delta append and
the registry insert re-processes that one file on the next pull.

This table belongs to PointlesSQL's own metadata DB (same Alembic
lineage as ``ingest_sources``); soyuz-catalog never sees it.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class AutoloaderFile(Base):
    """One source file the auto-loader has already ingested.

    Attributes:
        id: Auto-incremented primary key.
        ingest_source_id: FK to ``ingest_sources.id`` with ``ON DELETE
            CASCADE`` — registry rows follow their source.
        mapping_index: Position inside the source's ``table_mappings``
            list the file was pulled for.  Part of the uniqueness key
            because two mappings of one source may glob overlapping
            paths into different targets.
        file_path: Absolute path (or URL) of the ingested file.
        file_size: Size in bytes at ingest time (best-effort,
            nullable when the file vanished between append and stat).
        file_mtime: Modification timestamp at ingest time
            (best-effort, nullable like ``file_size``).
        processed_at: Wall-clock when the append landed.
    """

    __tablename__ = "autoloader_files"

    __table_args__ = (
        UniqueConstraint(
            "ingest_source_id",
            "mapping_index",
            "file_path",
            name="uq_autoloader_files_source_mapping_path",
        ),
        Index("ix_autoloader_files_source_mapping", "ingest_source_id", "mapping_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingest_source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ingest_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    mapping_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_mtime: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
