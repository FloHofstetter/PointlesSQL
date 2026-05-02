"""Cross-run anomaly inbox state.

Phase 18.6 turns the per-run anomaly chip into a cross-run inbox by
persisting two pieces of state:

* The verdict itself (``severity``/``metric``) lives as two columns
  on :class:`AgentRun` so the run-list page can paint a badge
  without recomputing the rolling baseline at render time.  Those
  columns are added in the same alembic migration as this table.
* The acknowledgement lifecycle lives in :class:`AnomalyAck`.
  Acked-but-not-dismissed-yet rows hide an anomaly from the inbox
  default view; permanent acks (NULL ``dismissed_until``) survive
  forever.  Composite-key uniqueness on ``(metric, bin_iso,
  bin_kind, group_value, group_kind)`` mirrors the natural
  identity of a cockpit anomaly point.

The aggregated anomaly *content* itself is rebuilt stateless from
:func:`audit_aggregator.anomalies` on every read — only ack state
needs persistence here.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class AnomalyAck(Base):
    """One acknowledgement for a cockpit anomaly bin.

    Attributes:
        id: Auto-incremented primary key.
        metric: Cockpit metric whose bin was acked (one of the
            :data:`audit_aggregator.VALID_METRICS` values, but stored
            as plain text so a future metric expansion does not require
            a schema migration).
        bin_iso: The bin's lexicographic timestamp prefix as
            :func:`audit_aggregator._bin_expr` emits it (10 chars for
            day, 16 for hour, 7 for week).
        bin_kind: ``hour`` / ``day`` / ``week`` — the bin width the
            ack applies to.  Different widths over the same instant
            ack independently.
        group_value: Optional group-by value (table FQN or principal
            email) when the anomaly was group-scoped; ``NULL`` for
            ungrouped anomalies.
        group_kind: ``table`` / ``principal`` / ``NULL`` — paired
            with ``group_value``.
        acked_by: Email of the user who acked.
        acked_at: UTC timestamp of the ack.
        dismissed_until: NULL = permanent ack; datetime = snooze
            expiry — after this instant the ack stops hiding the
            anomaly and the inbox shows it again.
        comment: Optional free-form note from the auditor.
    """

    __tablename__ = "anomaly_acks"
    __table_args__ = (
        UniqueConstraint(
            "metric",
            "bin_iso",
            "bin_kind",
            "group_value",
            "group_kind",
            name="uq_anomaly_acks_identity",
        ),
        Index(
            "ix_anomaly_acks_acked_at",
            "acked_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    bin_iso: Mapped[str] = mapped_column(String(32), nullable=False)
    bin_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    group_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    group_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    acked_by: Mapped[str] = mapped_column(String(255), nullable=False)
    acked_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dismissed_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
