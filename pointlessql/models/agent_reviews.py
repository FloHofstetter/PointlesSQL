"""Agent-review + review-destination ORM models (Sprint 19.2.1).

The Audit-Reviewer-Agent (a Hermes cron defined in
``docs/hermes-jobs/audit-reviewer-daily.json``) writes one
:class:`AgentReview` row per closed-day review and PointlesSQL fans
the same envelope out to every active :class:`ReviewDestination` via
:mod:`pointlessql.services.review_dispatcher`.

Two tables, no inter-table FK: destinations are admin-configured
once and shared across all reviews; the dispatcher records the
fan-out outcome inside ``AgentReview.delivered_to_json`` so each
review row stays self-contained for replay and audit-of-audit.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

REVIEW_SEVERITIES: frozenset[str] = frozenset({"ok", "warn", "critical"})

REVIEW_KIND_AUDIT = "audit_review"
REVIEW_KIND_MODEL_PROMOTION = "model_promotion"
REVIEW_KINDS: frozenset[str] = frozenset({REVIEW_KIND_AUDIT, REVIEW_KIND_MODEL_PROMOTION})


class AgentReview(Base):
    """One closed-day Audit-Reviewer-Agent run, persisted for replay.

    Severity is the worst of the three anomaly metrics the agent
    checked (rejects, errored_ops, external_writes).  ``summary_md``
    is the rendered Markdown that the cockpit card and any external
    sink display verbatim.  ``payload_json`` carries the raw
    tool-call transcript so a later replay can re-derive the summary
    without re-querying the audit lake.

    ``delivered_to_json`` is the dispatcher's fan-out log: each entry
    records ``{kind, url_hash, delivered_at, status_code}`` so an
    operator can verify which subscribers received the review without
    leaking the destination URLs themselves.

    Attributes:
        id: Auto-incremented primary key.
        run_id: FK to :class:`AgentRun`.  Nullable because the review
            itself runs as an agent_run, but historical imports +
            replays may not have a corresponding registered run.
        kind: Discriminator (Sprint 21.6) — ``audit_review`` for
            the Phase-19 daily anomaly review, ``model_promotion``
            for a champion/challenger swap.  Defaults to
            ``audit_review`` so existing rows backfill cleanly.
        period_start: Inclusive UTC lower bound of the review window.
        period_end: Exclusive UTC upper bound; must be strictly
            greater than ``period_start`` (CHECK constraint).
        severity: ``ok`` / ``warn`` / ``critical``.
        summary_md: Rendered Markdown digest, ≤ 50 KiB enforced at
            the API boundary.
        payload_json: Optional raw transcript / tool-call payload
            (≤ 1 MiB enforced at the API boundary).
        delivered_to_json: Optional JSON list of fan-out result
            entries.
        created_at: Insert timestamp.
    """

    __tablename__ = "agent_reviews"
    __table_args__ = (
        Index("ix_agent_reviews_period_end", "period_end"),
        Index("ix_agent_reviews_severity", "severity"),
        Index("ix_agent_reviews_kind", "kind"),
        CheckConstraint(
            "severity IN ('ok','warn','critical')",
            name="ck_agent_reviews_severity",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_agent_reviews_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="audit_review"
    )
    period_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text(), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    delivered_to_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewDestination(Base):
    """A single webhook sink that receives ``agent_review.posted`` events.

    Mirrors :class:`pointlessql.models.alerts.AlertDestination`'s
    surface so the dispatcher can reuse
    :func:`pointlessql.services.alert_dispatcher.dispatch_webhook`
    unchanged.  ``min_severity`` is the per-destination noise gate —
    set to ``warn`` by default so dashboards don't pinge for
    ``ok`` days.

    Attributes:
        id: Auto-incremented primary key.
        name: Admin-facing label (unique across the install).
        webhook_url: Outbound POST URL.  Plaintext at rest is
            acceptable for the MVP; encrypted-at-rest is a follow-up
            (same posture as ``AlertDestination.hmac_secret``).
        hmac_secret: Optional pre-shared secret; when set, the
            dispatcher signs the canonical body and attaches
            ``X-PointlesSQL-Signature: sha256=<hex>``.
        is_active: Inactive destinations are skipped by the
            dispatcher.
        min_severity: Lowest severity that triggers fan-out for this
            destination.  ``ok`` < ``warn`` < ``critical``.
        created_at: Insert timestamp.
    """

    __tablename__ = "review_destinations"
    __table_args__ = (
        Index("ix_review_destinations_active", "is_active"),
        UniqueConstraint("name", name="uq_review_destinations_name"),
        CheckConstraint(
            "min_severity IN ('ok','warn','critical')",
            name="ck_review_destinations_min_severity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    hmac_secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warn")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
