"""Agent SQL rewrite-attempt audit table (Phase 39 Sprint 39.2).

When the Hermes plugin's ``pql_query`` tool fires explain-first and
the cost-gate verdict says ``needs_approval=True``, the LLM is
encouraged to rewrite the SQL and retry.  Each rewrite outcome —
auto-success, auto-failure, escalation to human approval, or "agent
just approved the original" — lands here as one row so an auditor
can see the loop end-to-end on ``/runs/{run_id}``.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
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

VERDICT_AUTO_REWRITE_SUCCEEDED = "auto_rewrite_succeeded"
VERDICT_AUTO_REWRITE_FAILED = "auto_rewrite_failed"
VERDICT_HUMAN_APPROVAL_REQUIRED = "human_approval_required"
VERDICT_ORIGINAL_APPROVED = "original_approved"

REWRITE_VERDICTS: frozenset[str] = frozenset(
    {
        VERDICT_AUTO_REWRITE_SUCCEEDED,
        VERDICT_AUTO_REWRITE_FAILED,
        VERDICT_HUMAN_APPROVAL_REQUIRED,
        VERDICT_ORIGINAL_APPROVED,
    }
)


class RewriteAttempt(Base):
    """One agent SQL rewrite-attempt outcome inside an agent run.

    The ``original_sql_hash`` always refers to the *first* SQL the
    agent submitted in the rewrite loop (attempt 1's input).  The
    ``rewritten_sql_hash`` carries the agent's revised SQL when it
    rewrote; it is ``NULL`` for the ``human_approval_required`` and
    ``original_approved`` verdicts where no revision happened.

    The cost columns mirror the same asymmetry: ``original_cost`` is
    always the cost-gate's verdict on the original SQL,
    ``rewritten_cost`` the verdict on the revised SQL when one
    exists.  A Grafana panel computes savings as
    ``SUM(original_cost - rewritten_cost)`` filtered to the
    ``auto_rewrite_succeeded`` verdict.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this attempt belongs to.  Denormalised
            from parent :class:`AgentRun` so workspace-scoped audit
            reads + Grafana templating don't need a JOIN.
        agent_run_id: FK to :class:`AgentRun.id`.
        attempt_no: Monotonic per-run sequence number (1-indexed).
            Unique within an ``agent_run_id``; the plugin caps at 3
            before flipping to ``human_approval_required``.
        original_sql_hash: ``short_sql_hash`` (12-char SHA-256 prefix)
            of the agent's first SQL submission in this loop.
        rewritten_sql_hash: ``short_sql_hash`` of the revised SQL.
            ``None`` when no revision was attempted (the agent
            escalated immediately or accepted the original).
        original_cost: Cost-gate verdict on the original SQL — the
            heuristic ``max_cardinality × (1 + join_depth)`` from
            ``services/sql/cost_estimator.py``.
        rewritten_cost: Cost-gate verdict on the revised SQL.
            ``None`` when no revision was attempted.
        verdict: One of ``auto_rewrite_succeeded`` /
            ``auto_rewrite_failed`` / ``human_approval_required`` /
            ``original_approved``.  CHECK-constrained.
        reason: Optional free-text rationale the LLM sent alongside
            the rewrite.  Can be ``NULL``.
        created_at: Insert timestamp (UTC).
    """

    __tablename__ = "rewrite_attempts"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "attempt_no", name="uq_rewrite_attempts_run_attempt"),
        Index("ix_rewrite_attempts_run", "agent_run_id"),
        Index("ix_rewrite_attempts_workspace_created", "workspace_id", "created_at"),
        Index("ix_rewrite_attempts_verdict", "verdict"),
        CheckConstraint(
            "verdict IN "
            "('auto_rewrite_succeeded','auto_rewrite_failed',"
            "'human_approval_required','original_approved')",
            name="ck_rewrite_attempts_verdict",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    original_sql_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    rewritten_sql_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    original_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rewritten_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
