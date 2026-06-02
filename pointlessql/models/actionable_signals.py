"""``actionable_signals`` — the open-ledger for data-health problems.

A *signal* is one ongoing problem (an alert that is firing, an SLO
that is breached, a job that failed), not one check-tick.  The feed
live-unions every ``status='open'`` row into the activity stream, so
a data-health card always reflects the current state: the problem
clears, the row flips to ``resolved``, and the card drops from the
feed on the next fetch.

A **partial unique index** on ``dedupe_key`` while ``status='open'``
guarantees at most one open card per problem — a check that re-fires
every scheduler tick just bumps ``last_seen_at`` instead of stacking
duplicate cards.  This is the storm guard that lets continuously-
evaluated conditions feed the stream without drowning it.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from pointlessql.models.base import Base

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"


class ActionableSignal(Base):
    """One ongoing data-health / pipeline problem.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.  FK to ``workspaces.id``.
        signal_kind: What kind of problem — ``alert_firing``,
            ``slo_breach``, ``contract_violation``, ``freshness_stale``,
            ``job_failed``, ``ingest_failed``.  Drives the card's
            category + severity via the central registry.
        severity: ``warn`` / ``error`` — the card's left-border accent.
        entity_kind: What the problem is about (``dp`` / ``table`` /
            ``job`` / ``alert`` / ``run`` / ``ingest_source``).
        entity_ref: Reference within *entity_kind* (fqn / id / slug).
        dedupe_key: Natural key — ``signal_kind:workspace:kind:ref``
            (optionally with a sub-key).  Unique while ``open`` so a
            re-firing check never stacks duplicate cards.
        status: ``open`` (live, shown in the feed) or ``resolved``
            (the problem cleared; dropped from the feed).
        summary_md: One-line card text.
        payload_json: Optional JSON blob — metric, threshold, error
            snippet, action hints for the card.
        opened_at: When the problem was first observed.
        last_seen_at: Bumped on every re-observation while open, so a
            steady-state breach produces no new cards but keeps a
            freshness timestamp.
        resolved_at: When the problem cleared; ``None`` while open.
    """

    __tablename__ = "actionable_signals"

    __table_args__ = (
        # At most one OPEN signal per problem. Resolved rows are exempt
        # so the same problem can recur (open → resolved → open) and
        # keep a full history without violating the constraint.
        Index(
            "uq_actionable_signals_open",
            "dedupe_key",
            unique=True,
            sqlite_where=text("status = 'open'"),
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_actionable_signals_ws_status", "workspace_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(600), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_OPEN)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
