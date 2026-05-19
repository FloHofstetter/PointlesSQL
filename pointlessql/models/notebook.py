"""Native-editor notebook persistence: outputs + per-cell run history."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class Notebook(Base):
    """Stable UUID identity for a notebook (Phase 77.6).

    Pre-77.6 notebooks lived as bare files on disk referenced by
    ``file_path`` directly.  Path-keyed addressing breaks every
    social link / audit trail / lineage edge when the notebook is
    renamed.  77.6 adds this thin metadata table so the social
    layer can address notebooks by an opaque UUID
    (``kind='notebook', entity_ref=<uuid>``); rename becomes a
    single ``UPDATE notebooks SET file_path = ...`` without losing
    cross-references.

    Attributes:
        id: 36-char UUID4 string.  Stable across path renames.
        workspace_id: Tenant scope.
        file_path: Notebook path under the workspace's notebooks
            directory.  Unique per workspace.
        created_at: Wall-clock when the identity row was created.
    """

    __tablename__ = "notebooks"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "file_path",
            name="uq_notebooks_path_per_workspace",
        ),
        Index("ix_notebooks_path", "file_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookCellIdentity(Base):
    """Stable UUID identity for a single notebook cell (Phase 95).

    Named ``NotebookCellIdentity`` rather than ``NotebookCell`` to avoid
    a name collision with the transient doc-level
    :class:`pointlessql.services.notebook._doc.NotebookCell` dataclass.
    The table itself is ``notebook_cells`` (concise; no collision in
    SQL space).

    Per-cell social rows (comments / reactions / follows / tags) need a
    handle that survives source edits.  The on-disk ``.py`` is
    IDE-agnostic so no sidecar cell-UUID can ride the marker grammar;
    instead this table maps ``(notebook_id, content_hash)`` to a stable
    UUID at first save and tracks the current ``content_hash`` +
    ``ordinal_hint`` as the file evolves.

    Reconciliation happens on every save (see
    :mod:`pointlessql.services.notebook.cell_reconciliation`): pass 1
    does exact-hash matching (handles reorders), pass 2 a
    similarity-gated ordinal fallback (handles pure edits at the same
    position without stealing the UUID of a deleted-and-replaced
    neighbour), pass 3 mints fresh UUIDs for genuinely new cells.
    Unmatched survivors are soft-deleted via ``removed_at`` so the
    social anchor stays addressable from the notebook-level activity
    feed even after the cell is gone from the file.

    Attributes:
        id: 36-char UUID4 string — the stable cell identity.  Used as
            the second half of ``social_targets.entity_ref`` for kind
            ``'notebook_cell'`` (encoded as ``"{notebook_id}:{id}"``).
        workspace_id: Tenant scope, denormalised from the parent
            notebook so workspace-scoped queries don't need a join.
        notebook_id: FK to :class:`Notebook` with ``ondelete=CASCADE``.
        current_content_hash: Latest FNV-1a-64 hex of the cell's
            normalized source.  Drives pass-1 exact-hash matching.
        ordinal_hint: 0-based last-known position in the file.  Used
            as a tiebreak when multiple existing rows share the same
            hash and as the secondary key for pass-2 ordinal matching.
            Not a source of truth: cells can move freely.
        last_source_excerpt: First ≤500 chars of the last-seen source
            text.  Drives the pass-2 similarity gate that prevents
            the dark-corner case (delete cell + insert different cell
            at same position would otherwise steal the UUID).
        created_at: Wall-clock when the cell-identity row was minted.
        removed_at: Soft-delete tombstone, set when reconciliation
            cannot find this row in a later save.  Social rows stay
            reachable from the notebook activity feed; the inline
            cell-thread chip just doesn't render.
    """

    __tablename__ = "notebook_cells"

    __table_args__ = (
        Index(
            "ix_notebook_cells_live_ordinal",
            "notebook_id",
            "removed_at",
            "ordinal_hint",
        ),
        Index(
            "ix_notebook_cells_notebook_hash",
            "notebook_id",
            "current_content_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal_hint: Mapped[int] = mapped_column(Integer, nullable=False)
    last_source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    removed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotebookOutput(Base):
    """A single kernel output captured for the native notebook editor.

    Every iopub message the WS handler forwards to a client is also
    appended here so that reopening a notebook after kernel restart
    (or a page reload) replays the outputs without a 90-second
    ``pql.read_table()`` redo.

    Keyed by ``(file_path, content_hash, kernel_session_id,
    output_index)`` so ``kernel_session_id`` lets us keep pre- and
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
        workspace_id: FK to :class:`Workspace`.  Every persisted
            notebook output is workspace-scoped.
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
            :class:`pointlessql.models.agent._runs.AgentRun` when the
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
        Index("ix_notebook_outputs_agent_run", "agent_run_id"),
        Index("ix_notebook_outputs_workspace_path", "workspace_id", "file_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Every persisted notebook output is workspace-scoped.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
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
        workspace_id: FK to :class:`Workspace`.  Every cell run is
            workspace-scoped.
        execution_count: Jupyter's monotonic counter — ``None``
            while the cell is still running.
        status: ``"running"`` | ``"ok"`` | ``"error"`` |
            ``"aborted"`` (interrupted).
        started_at: When the ``execute_request`` landed.
        finished_at: When the kernel transitioned back to idle
            for this cell, or ``None`` while still busy.
        agent_run_id: UUID string of the owning
            :class:`pointlessql.models.agent._runs.AgentRun` when the
            run belongs to a Hermes-authored execution; ``None``
            for legacy editor sessions from before the agent-first
            pivot.
    """

    __tablename__ = "notebook_cell_runs"
    __table_args__ = (
        Index("ix_notebook_cell_runs_agent_run", "agent_run_id"),
        Index(
            "ix_notebook_cell_runs_workspace_session",
            "workspace_id",
            "kernel_session_id",
        ),
    )

    file_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kernel_session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Every cell-run lifecycle row is workspace-scoped.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
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
    :mod:`pointlessql.services.notebook.outputs`
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
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )

    __table_args__ = (
        Index(
            "ix_notebook_cell_run_sources_path_cell",
            "file_path",
            "content_hash",
            "started_at",
        ),
    )


class NotebookJobLink(Base):
    """Map a notebook path to the papermill jobs that target it.

    Phase 67.4 surface: the notebook editor's "Jobs of this notebook"
    panel needs to look up scheduled + recent jobs for the open
    notebook path. The :class:`~pointlessql.models.Job` table stores
    its ``notebook_path`` inside a JSON config blob (``Text`` column),
    which neither SQLite nor Postgres can index without a custom
    expression — so every editor open would scan the full jobs table
    via ``WHERE config LIKE '%"notebook_path":"<path>"%'``.

    This table is the trade-off: written opportunistically by the
    ``POST /api/jobs`` + ``POST /api/notebooks/run-once`` handlers
    when ``kind == "papermill"``, keyed for fast lookup on
    ``notebook_path``. It is a derived index; if a row goes stale the
    canonical state still lives in ``Job.config``.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`. Denormalised from the
            owning :class:`Job` so workspace-scoped reads can filter
            without joining ``jobs``.
        notebook_path: Relative notebook path the job's papermill
            config targets — identical to the string stored in
            ``Job.config['notebook_path']``.
        job_id: FK to :class:`Job` (``ON DELETE CASCADE`` so a
            future job-delete also clears this row).
        created_at: Timestamp when the link row was written.
    """

    __tablename__ = "notebook_job_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    notebook_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_notebook_job_link_path", "notebook_path"),
        Index("ix_notebook_job_link_workspace_path", "workspace_id", "notebook_path"),
        Index("ix_notebook_job_link_job_id", "job_id"),
    )
