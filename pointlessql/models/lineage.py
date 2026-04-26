"""Per-row lineage edges from PQL merge / write_table operations.

Sprint 15.3.  Operation-level lineage (``agent_run_operations``)
already says "op X produced N rows in Delta version V".  This table
adds the per-row map: "silver row R came from bronze rows S1, S2,
... via op O".  Sprint 15.4 walks the resulting graph backwards to
expose a row-trace UI.

Storage decision: PointlesSQL metadata DB rather than sibling Delta
``<fqn>_lineage`` tables.  Typical agent-ETL volumes (1k-100k rows
per run) fit easily; the Delta-table escalation path stays open as
a Phase-17+ option if a single run ever ships > 1M edges.

There is **no** UNIQUE constraint on
``(source_table, source_row_id, target_table, target_row_id)``: a
re-merge of the same rows produces a fresh edge with a different
``op_id``, and that history is the audit signal we want to keep.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class LineageRowEdge(Base):
    """One source-row → target-row map produced by a PQL merge / write.

    Attributes:
        id: Auto-incremented primary key.
        run_id: FK to :class:`AgentRun.id` — the run that produced
            this edge.
        op_id: FK to :class:`AgentRunOperation.id` — the specific
            primitive call.  Re-merges of identical rows yield new
            edges with new ``op_id``s, preserving merge history.
        source_table: Fully-qualified UC name the row was read from.
        source_row_id: ``_lineage_row_id`` value on the source row,
            originally minted on bronze autoload via the
            ``SHA-256("<file_sha>:<offset>")`` formula.
        target_table: Fully-qualified UC name the row was written
            to.
        target_row_id: Synthesised ``_lineage_row_id`` value on the
            target row, computed deterministically from
            ``SHA-256("<source_row_id>:<target_table>")`` so re-runs
            of the same merge produce identical target IDs and the
            walk-backward query has a stable join column.
        created_at: Wall-clock timestamp the edge row was inserted.
    """

    __tablename__ = "lineage_row_edges"

    __table_args__ = (
        Index("ix_lineage_row_edges_target", "target_table", "target_row_id"),
        Index("ix_lineage_row_edges_source", "source_table", "source_row_id"),
        Index("ix_lineage_row_edges_run", "run_id"),
        Index("ix_lineage_row_edges_op", "op_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    op_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_run_operations.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)
    target_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
