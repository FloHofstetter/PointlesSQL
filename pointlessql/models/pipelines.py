"""Declarative pipelines — materialized views + streaming tables.

Three tables backing the Lakeflow-shaped ETL surface:

* ``pipelines`` — one declarative pipeline per row.  The dataset
  definitions live as a JSON document (name, kind, SELECT,
  expectations) so the editor iterates without migrations; the
  engine derives the DAG from the SELECTs at run time.
* ``pipeline_runs`` — one row per execution with per-dataset
  metrics (rows written, expectation violations) as JSON.
* ``pipeline_cursors`` — the streaming-table state: one Delta
  version cursor per ``(pipeline, dataset, source table)`` so
  incremental runs only read the change feed since the last batch.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

PIPELINE_DATASET_KINDS: tuple[str, ...] = ("materialized_view", "streaming_table")
"""Dataset materialisations the engine knows how to refresh."""

PIPELINE_EXPECTATION_ACTIONS: tuple[str, ...] = ("warn", "drop", "fail")
"""What happens to rows violating an expectation."""

PIPELINE_RUN_STATES: tuple[str, ...] = ("running", "ok", "failed")
"""Lifecycle of one pipeline execution."""


class Pipeline(Base):
    """One declarative pipeline.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; pipelines are
            workspace-scoped like the rest of the metadata DB.
        slug: URL-visible identifier, unique across all rows.
        title: Human-readable name.
        description: Optional free-form description.
        owner_id: FK to ``users.id`` — runs execute as the owner.
        datasets: JSON list of dataset definitions
            (``{"name": <3-part target FQN>, "kind":
            "materialized_view"|"streaming_table", "sql": <SELECT>,
            "expectations": [{"name", "constraint", "action"}]}``).
        created_at: Timestamp when the pipeline was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "pipelines"

    __table_args__ = (
        Index("ix_pipelines_workspace", "workspace_id"),
        Index("ix_pipelines_owner", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    datasets: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineRun(Base):
    """One pipeline execution with per-dataset metrics.

    Attributes:
        id: Auto-incremented primary key.
        pipeline_id: FK to :class:`Pipeline` with ``ON DELETE
            CASCADE`` — history follows its pipeline.
        status: One of :data:`PIPELINE_RUN_STATES`.
        triggered_by: E-mail of the principal (or ``scheduler``).
        metrics: JSON list of per-dataset outcomes
            (``{"dataset", "kind", "rows_written", "skipped",
            "expectations": [{"name", "violations", "action"}]}``).
        error: Failure detail for ``failed`` runs.
        started_at: Wall-clock the run began.
        finished_at: Wall-clock the run ended (``None`` while
            running).
    """

    __tablename__ = "pipeline_runs"

    __table_args__ = (
        Index("ix_pipeline_runs_pipeline", "pipeline_id"),
        CheckConstraint(
            "status IN ('running', 'ok', 'failed')",
            name="ck_pipeline_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    triggered_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    metrics: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PipelineCursor(Base):
    """Streaming-table CDF cursor for one source of one dataset.

    Attributes:
        id: Auto-incremented primary key.
        pipeline_id: FK to :class:`Pipeline` with ``ON DELETE
            CASCADE``.
        dataset_name: The streaming table's target FQN.
        source_fqn: The upstream table the change feed is read from.
        last_version: Last Delta version already applied.
        updated_at: Timestamp of the most recent advance.
    """

    __tablename__ = "pipeline_cursors"

    __table_args__ = (
        UniqueConstraint(
            "pipeline_id",
            "dataset_name",
            "source_fqn",
            name="uq_pipeline_cursors_identity",
        ),
        Index("ix_pipeline_cursors_pipeline", "pipeline_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_fqn: Mapped[str] = mapped_column(String(256), nullable=False)
    last_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
