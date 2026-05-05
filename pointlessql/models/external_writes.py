"""External-write detection — unattributed Delta commits.

The PQL primitives (``autoload`` / ``merge`` / ``write_table`` /
``sql``) all emit ``agent_run_operations`` rows that carry the
``delta_version_after`` they produced.  Any Delta commit whose
version is *not* referenced by such a row is "unattributed" — a
write that bypassed every PQL primitive (raw
``deltalake.write_deltalake()``, Spark, ``cp`` of parquet, foreign
tools).

 closes that blind spot detection-side.  The
:mod:`pointlessql.services.external_write_scanner` walks
``DeltaTable.history()`` per UC table and INSERT-OR-IGNOREs into
``unattributed_writes`` for every commit not matched by an
``agent_run_operations`` row.  Detection-only — no storage-level
hard-block (that lives+ if a real customer asks; see
``project_full_autonomous_audit_critical_path.md``).
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


class UnattributedWrite(Base):
    """One Delta-log commit that no ``agent_run_operations`` row claims.

    The ``(workspace_id, table_fqn, delta_version)`` tuple is unique
    so re-scans are idempotent and the same commit can fan out to
    multiple workspaces (one row per workspace whose pinned-or-default
    catalog covers the FQN).  ``acknowledged_at`` /
    ``acknowledged_by`` capture the admin review action; ``NULL``
    ``acknowledged_at`` is the sidebar-badge counter's filter.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this unattributed-write attribution
            belongs to (Phase 28.1b).  The scanner fans out one row
            per workspace whose pinned catalog covers the FQN; if
            no workspace owns the catalog, attribution falls back to
            the seeded default workspace (id=1).
        table_fqn: Three-part UC name the commit landed on
            (``catalog.schema.table``).
        delta_version: Numeric Delta version the commit produced.
        commit_timestamp: ``CommitInfo.timestamp`` when known.
            ``None`` if Delta's history entry omits it.
        commit_info: JSON-encoded full ``CommitInfo`` payload from
            the Delta history entry.  Stored verbatim so a reviewer
            can inspect the raw commit metadata.  ``None`` when the
            history entry was unparseable.
        detected_at: Wall-clock timestamp the scanner recorded the
            row.
        acknowledged_at: Wall-clock timestamp an admin clicked
            "Acknowledge".  ``None`` until acknowledged.
        acknowledged_by: Email of the admin who acknowledged the
            row.  ``None`` until acknowledged.
    """

    __tablename__ = "unattributed_writes"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "table_fqn",
            "delta_version",
            name="uq_unattributed_writes_table_ver",
        ),
        Index("ix_unattributed_writes_acknowledged_at", "acknowledged_at"),
        Index("ix_unattributed_writes_detected_at", "detected_at"),
        Index("ix_unattributed_writes_workspace_table", "workspace_id", "table_fqn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    table_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    delta_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commit_timestamp: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    commit_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
