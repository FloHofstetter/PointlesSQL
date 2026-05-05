"""Forced audit-trail ORM models for agent runs.

Three tables back the supervision guarantee:

* :class:`AgentRunSource` stores the verbatim ``.py`` bytes the
  runtime declared at registration so a post-run file edit cannot
  erase the trail.  One row per run, enforced by the unique
  ``agent_run_id`` constraint.
* :class:`AgentRunOperation` records every PQL primitive call with
  input hash, target table, Delta version pre/post, and row count.
  Ordinal is monotonic per run (enforced by the composite uniqueness
  on ``(agent_run_id, ordinal)``); error rows stay in the trail with
  ``error_message`` populated and ``finished_at`` set.
* :class:`AgentRunEvent` mirrors :class:`AlertEvent` so CloudEvents
  lifecycle survives webhook outages — a row is inserted *before*
  webhook dispatch and the dispatcher updates ``outcome`` afterward.
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


class AgentRunSource(Base):
    """Captured ``.py`` source bytes for a single agent run.

    Inserted in the same transaction as the owning :class:`AgentRun`
    by ``POST /api/agent-runs`` so the registry can never hold a run
    record without the matching source.  The ``source_sha`` is
    re-computed server-side over the UTF-8 bytes; if the runtime
    sends a ``source_snapshot_sha`` field on :class:`AgentRun` and
    it disagrees, registration fails with 422 (tamper-detection).

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this source row belongs to (Phase
            28.1a).  Denormalised from parent :class:`AgentRun` so
            workspace-scoped reads don't need a JOIN.
        agent_run_id: FK to :class:`AgentRun.id`.  Unique — one
            source per run.
        source_bytes: UTF-8 encoded notebook source verbatim.  No
            normalisation, no comment-stripping — what the agent
            ran is what gets stored.
        source_sha: Lowercase hex SHA-256 of ``source_bytes``.
        captured_at: Wall-clock instant the source was captured
            (typically the run's ``started_at``).
    """

    __tablename__ = "agent_run_sources"
    __table_args__ = (
        Index("ix_agent_run_sources_sha", "source_sha"),
        Index("ix_agent_run_sources_workspace_run", "workspace_id", "agent_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 28.1a — denormalised from the parent AgentRun for
    # efficient workspace-scoped audit reads.  Set in the same
    # transaction as the parent insert.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False, unique=True
    )
    source_bytes: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunOperation(Base):
    """One PQL primitive call inside an agent run.

    Operations are emitted by the PQL layer when the
    ``POINTLESSQL_AGENT_RUN_ID`` env var (or an explicit
    ``agent_run_id`` constructor kwarg) is present.  Strict mode:
    if the insert fails (DB down, FK miss because the run was not
    registered) the primitive raises
    :class:`pointlessql.exceptions.AuditUnavailableError` *before*
    touching DuckDB or deltalake — a write without a trail must
    not happen.

    Failure path: when the underlying primitive raises, the
    operation row is still committed with ``finished_at = now()``
    and ``error_message = repr(exc)`` before re-raising, so the
    trail always shows the attempt.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this op belongs to (Phase 28.1a).
            Denormalised from parent :class:`AgentRun` so the
            forced audit-trail and lineage queries don't need a
            JOIN to derive scope.
        agent_run_id: FK to :class:`AgentRun.id`.
        ordinal: Monotonic per-run sequence number (1-indexed).
        op_name: One of ``"autoload"`` / ``"merge"`` /
            ``"write_table"`` / ``"sql"`` / ``"aggregate"`` /
            ``"rollback"`` / ``"train_model"``.  CHECK-constrained.
        params_json: JSON-encoded primitive arguments.  Excludes
            DataFrame contents — only call shape and stats.
        target_table: ``"catalog.schema.table"`` for writes; ``None``
            for ``sql`` (no single target).
        input_sha: SHA-256 of the canonical Arrow IPC bytes for
            writes / merges, ``None`` for SQL reads.  For autoload
            it's the SHA-256 of the concatenated per-file SHAs so
            the file-level provenance from
            :class:`AutoloadCheckpoint` survives in one digest.
        rows_affected: Row count produced by the operation, or
            ``None`` when the primitive doesn't expose one.
        delta_version_before: ``DeltaTable.version()`` immediately
            before the write.  ``None`` when the table didn't exist
            yet or for read-only operations.
        delta_version_after: ``DeltaTable.version()`` immediately
            after the write.  Together with the ``before`` field
            this lets a reviewer time-travel-recover the exact
            state the run produced.
        started_at: Wall-clock instant the primitive entered.
        finished_at: Wall-clock instant the primitive exited
            (success or failure).  ``None`` only when the row
            represents a still-in-flight call (process killed
            mid-op).
        error_message: ``repr(exc)`` when the primitive raised.
            ``None`` on success.
        mlflow_run_id:  cross-link — populated by
            :func:`record_operation` when MLflow is active.  ``None``
            for non-ML ops.
        training_params_json: JSON blob with ``params``
            and ``metrics`` sub-keys captured by
            :func:`pql.training_context()`.  ``None`` for non-training
            ops.
        env_snapshot: advisory JSON snapshot of the
            host environment (Python version, top-level package
            versions, GPU list when torch is installed).  Cached
            once per PointlesSQL process so the hot path stays
            cheap.  ``None`` when capture failed at start-up.
        warnings_json: BUG-grand-08 — JSON blob with a ``markers``
            sub-key listing non-fatal post-commit failures
            (lineage emit / edges / rejects / column / value).
            ``error_message`` stays reserved for "the primitive
            itself raised"; this column carries side-effect
            warnings without poisoning the operation's status.
            ``None`` when no marker was stamped.
    """

    __tablename__ = "agent_run_operations"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "ordinal", name="uq_agent_run_operations_ordinal"),
        Index("ix_agent_run_operations_run", "agent_run_id"),
        Index(
            "ix_agent_run_operations_workspace_run",
            "workspace_id",
            "agent_run_id",
        ),
        CheckConstraint(
            "op_name IN "
            "('autoload','merge','write_table','sql','aggregate','rollback','train_model')",
            name="ck_agent_run_operations_op_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 28.1a — denormalised from parent AgentRun for efficient
    # workspace-scoped audit reads.  All lineage / value-change /
    # external-write rows that hang off this op derive their workspace
    # by JOIN, so this is the single canonical column per op.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    op_name: Mapped[str] = mapped_column(String(32), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rows_affected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta_version_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delta_version_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #  cross-link: populated by record_operation when MLflow
    # is active (see :mod:`pointlessql.services.agent_runs.mlflow_detector`).
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # autolog snapshot ({"params": {...}, "metrics": {...}}).
    training_params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # advisory hardware/library fingerprint
    # (Python version, top-level package versions, GPU list).
    env_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    # BUG-grand-08 — non-fatal side-effect markers (lineage emit /
    # edge insert / reject / column / value-change failures).  JSON:
    # ``{"markers": [str, ...]}``.  ``error_message`` stays reserved
    # for "the primitive itself raised".
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRunEvent(Base):
    """One CloudEvents lifecycle envelope for an agent run.

    Every CloudEvents envelope is persisted so a webhook outage
    can't lose the trail.  The row is inserted with
    ``outcome = "pending"`` *before* the dispatch call; the
    dispatcher updates the column to ``"delivered"`` /
    ``"delivery_failed"`` / ``"no_destination"``.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this event belongs to (Phase 28.1a).
            Denormalised from parent :class:`AgentRun`.
        agent_run_id: FK to :class:`AgentRun.id`.
        event_id: CloudEvents ``id`` field (uuid4 hex), unique
            so receivers can dedup across retries.
        event_type: One of ``pointlessql.agent_run.{started,
            completed, failed}`` — see
            :data:`pointlessql.services.agent_runs.events.AGENT_RUN_EVENT_TYPES`.
        fired_at: When :func:`emit_agent_run_event` built the envelope.
        outcome: ``pending`` | ``delivered`` | ``delivery_failed`` |
            ``no_destination``.  CHECK-constrained.
        payload_json: Full CloudEvents 1.0 envelope as JSON text,
            for replay and debug without reconstruction.
    """

    __tablename__ = "agent_run_events"
    __table_args__ = (
        Index("ix_agent_run_events_fired", "agent_run_id", "fired_at"),
        Index("ix_agent_run_events_workspace_run", "workspace_id", "agent_run_id"),
        CheckConstraint(
            "outcome IN ('pending','delivered','delivery_failed','no_destination')",
            name="ck_agent_run_events_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 28.1a — denormalised from parent AgentRun.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fired_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class AgentRunToolCall(Base):
    """One LLM tool invocation inside an agent run.

    Distinct from :class:`AgentRunOperation` (PQL primitive writes)
    and :class:`AgentRunEvent` (CloudEvent dispatch outcome).  Tool
    calls are the LLM's *reasoning trace*: which tool the model
    chose, what args it passed, and a short summary of the result.
    The Hermes plugin's ``post_tool_call`` hook posts here for any
    tool whose name starts with ``pql_``.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this tool call belongs to (Phase
            28.1a).  Denormalised from parent :class:`AgentRun`.
        agent_run_id: FK to :class:`AgentRun.id`.
        tool_name: Hermes tool name, e.g. ``pql_query`` or
            ``pql_get_table``.
        args_json: JSON-encoded args passed to the tool.  Trimmed
            to a sensible cap by the plugin if huge.
        result_summary: Short summary of the tool's return value
            (first ~500 chars after the LLM-friendly truncation).
            ``None`` for fire-and-forget calls.
        duration_ms: Wall-clock duration of the tool call from the
            plugin's perspective.  ``None`` when the plugin could
            not measure it.
        called_at: Wall-clock instant the tool finished (the hook
            fires post-call).
    """

    __tablename__ = "agent_run_tool_calls"
    __table_args__ = (
        Index(
            "ix_agent_run_tool_calls_run",
            "agent_run_id",
            "called_at",
        ),
        Index(
            "ix_agent_run_tool_calls_workspace_run",
            "workspace_id",
            "agent_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 28.1a — denormalised from parent AgentRun.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    called_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
