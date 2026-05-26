"""IngestSource model for the Ingest UI.

A configured connection to an external system (file upload, S3, HTTP,
Postgres, MySQL, SQLite, Parquet glob) that PointlesSQL can pull rows
from on a schedule.  The seven connector kinds share one row shape;
``kind`` discriminates which sub-section of ``config`` / ``secrets``
matters.

The schedule itself lives on the ``jobs`` table (one ``Job`` row per
active source, ``Job.kind = 'ingest_pull'``, ``Job.config`` carries
``{source_id, mapping_index}``).  Per-mapping execution history reads
through ``job_runs``.  Ingest reuses the existing job scheduler
verbatim — no new scheduling tables.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

# The seven first-party connector kinds shipped .  Any
# kind string that is not in this tuple is rejected at create-time
# by ``ingest_routes/sources.py``.
INGEST_SOURCE_KINDS: tuple[str, ...] = (
    "file_upload",
    "s3",
    "http",
    "postgres",
    "mysql",
    "sqlite",
    "parquet_glob",
)

# Per-mapping pull modes.  ``full`` overwrites the target every pull;
# ``incremental`` requires ``high_water_col`` and reads only rows
# newer than the previously-stored watermark.
INGEST_PULL_MODES: tuple[str, ...] = ("full", "incremental")


class IngestSource(Base):
    """A configured external data source for scheduled pulls.

    One row per "connection the user wired up".  The seven connector
    kinds share this row shape and discriminate via the ``kind`` column.

    ``config`` carries non-secret connection parameters (host, port,
    bucket, file path, glob pattern, etc.) as a JSON-encoded string.
    ``secrets`` carries plaintext credentials (Postgres password, S3
    secret key, HTTP bearer token) in a JSON-encoded string column —
    redacted on every API GET, only fully readable inside the executor
    that runs under the source's owner.

    ``table_mappings`` is a JSON-encoded list of
    ``{source_table, target_fqn, mode, high_water_col,
    last_high_water_value, last_pull_stats}`` dicts.  One entry per
    table the user wants pulled.  File-based connectors (``file_upload``,
    ``http``, ``s3``, ``parquet_glob``) have exactly one mapping; SQL
    connectors may have many.

    ``job_id`` links to the ``Job`` row that owns the cron schedule.
    ``NULL`` when the source is paused / unscheduled.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``.  Workspace-scoped per
            FK to ``users.id``.  The creator; pulls run
            under their principal so soyuz authorization applies.
        name: Human-readable name, unique within the workspace.
        kind: One of :data:`INGEST_SOURCE_KINDS`.
        config: JSON-encoded non-secret connection parameters.
        secrets: JSON-encoded plaintext credentials.  Redacted on
            every API read.
        table_mappings: JSON-encoded list of per-table pull mappings.
        job_id: FK to ``jobs.id`` — the cron-scheduled pull job.
            ``NULL`` when no schedule is configured.
        is_active: When ``False`` the scheduler skips this source and
            manual "Pull now" is rejected.
        created_at: Timestamp when the source was registered.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "ingest_sources"

    __table_args__ = (
        Index("uq_ingest_sources_workspace_name", "workspace_id", "name", unique=True),
        Index("ix_ingest_sources_workspace_kind", "workspace_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    secrets: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    table_mappings: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
