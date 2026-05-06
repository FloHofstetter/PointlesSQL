"""Expected upstream-producer registry for the Phase-40 freshness check.

One row per ``(workspace, target_table, producer)`` triple captures
"this table should receive at least one inbound OpenLineage event
from this producer every ``max_silence_minutes`` minutes".  The
Sprint-40.4 freshness compute walks this registry to surface stale
upstream feeds on the table-detail page and (optionally, via
``last_alerted_at`` dedup) emit a CloudEvents alert envelope.

Storage decision: PointlesSQL metadata DB (not soyuz / not external).
The registry is small (~10s-100s of rows in a typical install) and
the read paths are workspace-scoped.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class ExpectedLineageInbound(Base):
    """One ``(target_table, producer, max_silence_minutes)`` expectation.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this expectation belongs to.
        target_table_full_name: Three-part UC name of the table we
            expect inbound lineage for.
        producer: OpenLineage ``job.namespace`` of the expected
            upstream feed.
        max_silence_minutes: Threshold for freshness — if no inbound
            edge from *producer* into *target_table_full_name* has
            been seen for this many minutes, the freshness check
            considers the producer stale.
        is_active: Admin enable/disable.  An inactive row stays for
            audit history but is skipped by the freshness compute.
        last_alerted_at: Wall-clock of the most recent staleness
            alert envelope emitted for this row.  Used for re-alert
            suppression so a continuously-stale producer doesn't
            flood downstream sinks every poll.
        created_at: Wall-clock the row was registered.
    """

    __tablename__ = "expected_lineage_inbound"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "target_table_full_name",
            "producer",
            name="uq_expected_lineage_inbound_ws_table_producer",
        ),
        CheckConstraint(
            "max_silence_minutes > 0",
            name="ck_expected_lineage_inbound_silence_positive",
        ),
        Index(
            "ix_expected_lineage_inbound_workspace_active",
            "workspace_id",
            "is_active",
        ),
        Index("ix_expected_lineage_inbound_target", "target_table_full_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    target_table_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    producer: Mapped[str] = mapped_column(String(255), nullable=False)
    max_silence_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_alerted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
