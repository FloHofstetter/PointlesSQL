"""Agent-run registry — supervision primitive for external runtimes.

PointlesSQL is the *registry + store* for agent workloads; the
actual execution happens in Hermes (or any other runtime) which
POSTs lifecycle transitions here.  One row per run carries every
piece of supervision state the control-room, CloudEvents emitter,
and run-detail view need, without hiding fields inside a JSON blob.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_NEEDS_APPROVAL = "needs_approval"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

VALID_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_QUEUED,
        STATUS_RUNNING,
        STATUS_NEEDS_APPROVAL,
        STATUS_APPROVED,
        STATUS_DENIED,
        STATUS_SUCCEEDED,
        STATUS_FAILED,
    }
)

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_DENIED,
    }
)


class AgentRun(Base):
    """One supervised agent execution, registered from an external runtime.

    The id is a caller-provided UUID string so Hermes can POST the
    same id on ``/api/agent-runs`` (create) and later
    ``/api/agent-runs/{id}/finish`` (terminate) without a round-trip
    to learn the PointlesSQL-assigned key.  ``tables_touched`` is a
    JSON-encoded list of three-part UC names, chosen over a
    side-table because the list is read as a whole in the control-
    room and never indexed on its own.

    Attributes:
        id: UUIDv4 string supplied by the runtime on creation.
        principal: ``X-Principal`` header value, typically the user
            email the agent acts on behalf of.  Nullable so a purely
            background agent can still register.
        agent_id: Free-form runtime-side identifier (e.g. Hermes's
            agent role).  Pairs with ``principal`` for filtering in
            the control-room.
        notebook_path: Path of the ``.py`` notebook the run executes,
            relative to the notebooks dir.  Required — the
            run-detail view renders the cell card deck from it.
        source_snapshot_sha: Optional content hash of the notebook
            source the runtime actually ran.  Lets the detail view
            detect edit-races between run start and page render.
        status: One of :data:`VALID_STATUSES`.  External runtime
            transitions the state machine; server refuses
            transitions out of :data:`TERMINAL_STATUSES`.
        cost_est: Optional EXPLAIN-gate estimate.  ``Decimal`` keeps
            the value monetarily-exact across drivers.
        tables_touched: JSON-encoded list of UC table names the run
            reads or writes; populated by the runtime via the
            ``pql_*`` tool surface.
        started_at: Wall-clock run-creation timestamp.
        finished_at: Set on terminal transition; ``None`` while the
            run is still active.
        exit_code: Optional integer surfaced from the runtime's
            process wrapper.
        approved_by: Email of the admin who clicked "Approve" in the
            control-room; ``None`` until approval happens.
        approved_at: Timestamp of the approval.
        denied_reason: Free-form denial text.  Mutually exclusive
            with ``approved_by``; the state machine enforces the
            pairing.
        runtime_versions: JSON-encoded mapping of runtime-side
            dependency versions (Python, ``pql``, ``deltalake``,
            ``duckdb``, ...).  Required by ``POST /api/agent-runs``;
            the column is nullable so legacy rows from before the
            requirement landed stay queryable.
        cost_gate_trigger: JSON-encoded snapshot of the EXPLAIN plan
            the cost gate fired on, plus the threshold + estimated
            cost + engine that produced the verdict.  Populated by
            the runtime when it transitions a run to ``denied``
            because of a cost-gate verdict; ``None`` for runs that
            never hit the gate.  Lets a reviewer see WHY a run was
            blocked without re-running the query.
    """

    __tablename__ = "agent_runs"

    __table_args__ = (
        Index("ix_agent_runs_started_at", "started_at"),
        Index("ix_agent_runs_principal", "principal"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    principal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notebook_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_snapshot_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_est: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    tables_touched: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    denied_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_versions: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_gate_trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    #  cross-link: populated by the operation_context recorder
    # when an op detects an active MLflow run via mlflow_detector.  Index
    # is added in alembic q7m9o1p3r5t7 so /api/runs/{id}/ml-context can
    # join to MLflow without a full scan.
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
