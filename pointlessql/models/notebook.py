"""Native-editor notebook persistence: outputs + per-cell run history."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookOutput(Base):
    """A single kernel output captured for the native notebook editor.

    Every iopub message the WS handler forwards to a client is also
    appended here so that reopening a notebook after kernel restart
    (or a page reload) replays the outputs without a 90-second
    ``pql.read_table()`` redo.

    Keyed by ``(file_path, content_hash, kernel_session_id, output_index)``
    per ADR 0001 — ``kernel_session_id`` lets us keep pre- and
    post-restart histories side by side for free (a future iteration
    can surface "previous session" as a toggle without a schema
    change).  The frontend renders by reading the whole
    ``(file_path, content_hash)`` pair's rows for the latest session.

    The identity column is ``content_hash`` —
    ``sha256(normalized_source)[:16]`` computed at load time, not an
    opaque UUID the marker carries.  That makes ``.py`` notebooks
    generically editable in VSCode / Vim without a PointlesSQL-specific
    ID mechanism.

    Attributes:
        id: Auto-incremented primary key.
        file_path: Notebook path relative to the notebooks dir —
            the same string the editor's URL and the jupytext
            round-trip use.
        content_hash: 16-char hex prefix of the SHA-256 of the
            cell's normalized source, stable across reloads and
            unchanged by whitespace-only edits.
        kernel_session_id: UUID of the :class:`KernelSession` the
            message came from (bumps on restart).
        output_index: 0-based position within the cell's outputs
            for this kernel session.
        msg_type: Jupyter message type — ``stream`` /
            ``execute_result`` / ``display_data`` / ``error``.
            ``status`` + ``execute_input`` are *not* persisted
            (they carry no output content).
        mime_bundle: JSON-encoded ``content`` dict of the original
            Jupyter message.  Binary mimes travel base64 per the
            Jupyter convention.
        output_metadata: Optional JSON-encoded ``metadata`` dict.
        created_at: When the message was forwarded.
        agent_run_id: UUID string of the owning
            :class:`pointlessql.models.agent_runs.AgentRun` when the
            output belongs to a Hermes-authored run; ``None`` for
            legacy editor sessions from before the agent-first
            pivot.
    """

    __tablename__ = "notebook_outputs"
    __table_args__ = (
        UniqueConstraint(
            "file_path",
            "content_hash",
            "kernel_session_id",
            "output_index",
            name="uq_notebook_outputs_position",
        ),
        Index("ix_notebook_outputs_lookup", "file_path", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kernel_session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    output_index: Mapped[int] = mapped_column(Integer, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_bundle: Mapped[str] = mapped_column(Text, nullable=False)
    output_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class NotebookCellRun(Base):
    """Execution lifecycle for one cell of one kernel session.

    Companion to :class:`NotebookOutput` — tracks when a cell
    started, whether it succeeded, the ``execution_count`` the
    kernel gave it, and when it finished.  The editor uses it to
    show "cell X is running" + the execution counter; elapsed-time
    pills can be added without a schema change.

    Primary key is the same ``(file_path, content_hash,
    kernel_session_id)`` triple as the outputs; a cell can be
    re-run within the same session but only the latest run's
    status is kept (re-execute == UPDATE).

    The identity column is ``content_hash`` (``sha256(source)[:16]``)
    — see :class:`NotebookOutput` for the rationale.

    Attributes:
        file_path: Notebook path relative to the notebooks dir.
        content_hash: Content-hash of the cell's normalized source.
        kernel_session_id: Session UUID (bumps on restart).
        execution_count: Jupyter's monotonic counter — ``None``
            while the cell is still running.
        status: ``"running"`` | ``"ok"`` | ``"error"`` |
            ``"aborted"`` (interrupted).
        started_at: When the ``execute_request`` landed.
        finished_at: When the kernel transitioned back to idle
            for this cell, or ``None`` while still busy.
        agent_run_id: UUID string of the owning
            :class:`pointlessql.models.agent_runs.AgentRun` when the
            run belongs to a Hermes-authored execution; ``None``
            for legacy editor sessions from before the agent-first
            pivot.
    """

    __tablename__ = "notebook_cell_runs"

    file_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kernel_session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class NotebookCellRunSource(Base):
    """One execute_request's source snapshot + lifecycle.

    Sibling to :class:`NotebookCellRun` — that table upserts on
    ``(file_path, content_hash, kernel_session_id)`` so a re-run
    within the same session overwrites the prior row.  This table
    inserts a fresh row per execute, capturing the source the
    kernel actually saw + the lifecycle status / timestamps +
    ``execution_count``, so the editor's per-cell run-history
    popover can show "last N runs" with diffs and a re-run button.

    No FK to ``notebook_cell_runs`` — the link is logical via the
    indexed columns.  Cascade-on-delete lives in
    :mod:`pointlessql.services.notebook_outputs`
    (cascade-via-service pattern).

    The identity column is ``content_hash`` (``sha256(source)[:16]``);
    history rows for a given cell therefore survive whitespace-only
    edits and reordering but split on meaningful source changes —
    intentional, so the popover groups by what the user actually
    changed.

    Attributes:
        id: Auto-incremented primary key.
        file_path: Notebook path relative to the notebooks dir.
        content_hash: Content-hash of the cell's normalized source
            at the time of the run.
        kernel_session_id: Session UUID (bumps on kernel restart).
        execution_count: Jupyter's monotonic counter — ``None``
            while the cell is still running, set on execute_reply.
        source: Verbatim cell source the kernel saw.  For SQL cells
            this is the wrapped ``__pql_sql_run(...)`` snippet, not
            the raw SELECT; history is what was executed, not what
            was typed.
        started_at: When the ``execute_request`` landed.
        finished_at: When ``execute_reply`` arrived, or ``None``
            while still running.
        status: ``"running"`` | ``"ok"`` | ``"error"`` |
            ``"aborted"`` (interrupted) — denormalised from
            :class:`NotebookCellRun` to spare the popover query a
            join.
    """

    __tablename__ = "notebook_cell_run_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kernel_session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")

    __table_args__ = (
        Index(
            "ix_notebook_cell_run_sources_path_cell",
            "file_path",
            "content_hash",
            "started_at",
        ),
    )
