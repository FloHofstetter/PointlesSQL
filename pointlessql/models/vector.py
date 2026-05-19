"""Phase 92 — ``VectorIndex`` ORM for the vector-search primitive.

One row per ``(workspace, catalog, schema, table, column)`` index
backed by a duckdb-vss ``.duckdb`` file on disk.  The row carries
just enough metadata to:

* let the merge post-commit hook discover indices that need a
  rebuild after a mutation on the source table,
* let the REST list endpoint enumerate indices for a table-detail
  page so the UI tab gates on existence,
* let the search route re-resolve the embedder + dim without
  reading the on-disk file's ``meta`` table first.

The on-disk DuckDB file's ``meta`` row carries the same data
(plus the live HNSW parameters) so a cross-machine workspace
export → import remains lossless even when the metadata DB is
rebuilt fresh.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class VectorIndex(Base):
    """Workspace-scoped record of a duckdb-vss HNSW index.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``.
        catalog: UC catalog name of the indexed table.
        schema: UC schema name of the indexed table.
        table: UC table name of the indexed table.
        column: Indexed text column on the table.
        dim: Embedding dimensionality.
        model: Provider-specific model identifier (e.g.
            ``"all-MiniLM-L6-v2"``).
        embedder: Registry key — one of ``"sentence_transformers"``,
            ``"openai"``, ``"hermes"``.
        metric: ``"cosine"`` (default), ``"l2"``, or ``"ip"``.
        hnsw_m: HNSW ``m`` build parameter persisted for rebuild.
        hnsw_ef_construction: HNSW ``ef_construction`` build
            parameter persisted for rebuild.
        index_path: Absolute filesystem path to the ``.duckdb`` file.
        delta_version_indexed: Most recent Delta table version this
            index reflects; ``None`` until first build completes.
        last_built_at: Timestamp of the most recent successful build.
        last_built_rows: Row count from the last build.
        last_error: Most recent build / rebuild error message, or
            ``None`` when the index is healthy.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    __tablename__ = "vector_indices"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "catalog",
            "schema",
            "table",
            "column",
            name="uq_vector_indices_target",
        ),
        Index(
            "ix_vector_indices_table",
            "workspace_id",
            "catalog",
            "schema",
            "table",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False
    )
    catalog: Mapped[str] = mapped_column(String(255), nullable=False)
    schema: Mapped[str] = mapped_column(String(255), nullable=False)
    table: Mapped[str] = mapped_column(String(255), nullable=False)
    column: Mapped[str] = mapped_column(String(255), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedder: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cosine", server_default="cosine"
    )
    hnsw_m: Mapped[int] = mapped_column(
        Integer, nullable=False, default=16, server_default="16"
    )
    hnsw_ef_construction: Mapped[int] = mapped_column(
        Integer, nullable=False, default=128, server_default="128"
    )
    index_path: Mapped[str] = mapped_column(Text, nullable=False)
    delta_version_indexed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_built_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_built_rows: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )
