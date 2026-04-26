"""Per-row lineage edges and rejects from PQL merge / write_table.

Sprint 15.3 introduced :class:`LineageRowEdge` — one row per
``(source_row, target_row, op)`` mapping that lets the row-trace UI
walk silver back to bronze.  Sprint 15.5.3 adds
:class:`LineageRowReject` — one row per source row that was supposed
to land but didn't, with an enumerated ``reason`` so the UI can
explain "47 of 50 rows survived; here are the 3 that were dropped".

Storage decision: PointlesSQL metadata DB rather than sibling Delta
``<fqn>_lineage`` tables.  Typical agent-ETL volumes (1k-100k rows
per run) fit easily; the Delta-table escalation path stays open as
a Phase-17+ option if a single run ever ships > 1M edges.

There is **no** UNIQUE constraint on either table.  For edges, a
re-merge of the same rows produces a fresh edge with a different
``op_id``, and that history is the audit signal we want to keep.
For rejects, a re-run that drops the same rows again is also
informative (operator wants to see "this still fails").
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

REJECT_REASONS = (
    "on_key_null",
    "schema_mismatch",
    "duplicate_in_source",
    "merge_predicate_excluded",
    "other",
)

TRANSFORM_KINDS = (
    "identity",
    "rename",
    "derived",
    "aggregate",
    "unknown_origin",
    "sql_select",
    "sql_function",
    "sql_unknown",
)


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    op_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_run_operations.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)
    target_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LineageRowReject(Base):
    """One source row that was supposed to land in *target_table* but didn't.

    Sprint 15.5.3 — opt-in capture via ``pql.merge(track_rejects=True)``.
    The default is ``False`` because pre-merge set-diff against the
    source has a small per-row pandas cost; production callers that
    want the audit trail flip it on explicitly.

    Attributes:
        id: Auto-incremented primary key.
        run_id: FK to :class:`AgentRun.id`.
        op_id: FK to :class:`AgentRunOperation.id` — the merge / write
            call that decided to drop this row.
        source_table: Fully-qualified UC name the rejected row came
            from.  Required so the row-trace UI can link to the
            originating row from the reject view.
        source_row_id: ``_lineage_row_id`` of the rejected row.
            Required for the same reason.
        reason: Enum-as-string describing why the row didn't land —
            one of :data:`REJECT_REASONS`.  CHECK-constrained.
        detail: Optional free-form context (e.g. the offending
            value, the offending column).  Kept short — it goes onto
            a tab in the run-detail UI, not into a log.
        created_at: Wall-clock timestamp the reject row was inserted.
    """

    __tablename__ = "lineage_row_rejects"

    __table_args__ = (
        Index("ix_lineage_row_rejects_run", "run_id"),
        Index("ix_lineage_row_rejects_op", "op_id"),
        Index("ix_lineage_row_rejects_source", "source_table", "source_row_id"),
        CheckConstraint(
            "reason IN ('on_key_null','schema_mismatch','duplicate_in_source',"
            "'merge_predicate_excluded','other')",
            name="ck_lineage_row_rejects_reason",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    op_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_run_operations.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LineageColumnMap(Base):
    """One source-column → target-column mapping produced by a PQL op.

    Sprint 15.6.1 — sibling to :class:`LineageRowEdge` covering the
    orthogonal column dimension.  Each row says "for op *op_id*,
    target column *target_table.target_column* was fed by source
    column *source_table.source_column* via *transform_kind*".

    Volume-wise this table is bounded by **schema breadth** (number
    of output columns × sources per column), not by row count, so a
    Medallion run that produces 100k row edges typically adds only a
    few dozen column-map rows.  Best-effort writes mirror
    :class:`LineageRowEdge` — a DB hiccup never rolls back the Delta
    write, and a per-op cap (1000 edges) prevents pathological
    ``pql.sql`` queries from blowing the table up.

    Attributes:
        id: Auto-incremented primary key.
        run_id: FK to :class:`AgentRun.id` — the run that produced
            this edge.
        op_id: FK to :class:`AgentRunOperation.id` — the specific
            primitive call.
        source_table: Fully-qualified UC name of the source table,
            or ``NULL`` when ``transform_kind == "unknown_origin"``
            (audit columns, undeclared derived columns).
        source_column: Source column name; ``NULL`` for
            ``unknown_origin``.
        target_table: Fully-qualified UC name the column lives in.
        target_column: Target column name.
        transform_kind: How the source feeds the target — one of
            :data:`TRANSFORM_KINDS`.  CHECK-constrained.
        transform_detail: Optional free-form context.  Stores the
            aggregation function name for ``aggregate`` edges, the
            rendered subexpression for ``sql_function`` edges, the
            string ``"audit"`` for ``unknown_origin`` audit columns,
            and the string ``"synth_target_row_id"`` for the synthesised
            ``_lineage_row_id`` cross-stage edge.
        created_at: Wall-clock timestamp the row was inserted.
    """

    __tablename__ = "lineage_column_map"

    __table_args__ = (
        Index("ix_lineage_column_map_run", "run_id"),
        Index("ix_lineage_column_map_op", "op_id"),
        Index("ix_lineage_column_map_target", "target_table", "target_column"),
        Index("ix_lineage_column_map_source", "source_table", "source_column"),
        CheckConstraint(
            "transform_kind IN ('identity','rename','derived','aggregate',"
            "'unknown_origin','sql_select','sql_function','sql_unknown')",
            name="ck_lineage_column_map_transform_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    op_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_run_operations.id"), nullable=False
    )
    source_table: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    transform_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    transform_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
