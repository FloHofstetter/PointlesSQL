"""Native-editor notebook persistence: outputs + per-cell run history."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
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


class NotebookCellProvenance(Base):
    """Append-only audit row for AI-assistant cell changes (Phase 96).

    Every accepted :class:`NotebookCellProposal` writes one row here
    once the user saves the notebook and the cell-reconciliation
    pass has minted the final ``cell_uuid``.  The table is *strictly
    append-only* — never updated, never deleted (a tombstone on the
    cell identity row implicitly tombstones the chain too).  This is
    the shape Phase 97's revision-history sprint reads to render
    "proposed by agent A at T1; fixed by agent B at T2".

    Why a separate table, not columns on
    :class:`NotebookCellIdentity`:

    * Identity is mutable (``current_content_hash`` /
      ``ordinal_hint`` change on every save).  Mutating identity
      columns would lose the chain.
    * One cell can accumulate many provenance rows (initial propose
      + N subsequent fixes + M explanations).  Cardinality belongs
      in a child table, not a single-row column.

    Attributes:
        id: Auto-incremented primary key.
        cell_uuid: FK to :class:`NotebookCellIdentity.id` — the
            stable cell identity the proposal landed on.
        agent_run_id: FK to :class:`AgentRun` — the agent run that
            authored the proposal.  Equal to the chat session's
            ``agent_run_id`` for chat-driven proposals.
        proposal_id: FK to
            :class:`NotebookCellProposal.proposal_id` — the
            originating draft, so the audit trail can look up
            ``rationale`` / ``new_source`` if needed.
        action: ``"propose"`` | ``"fix"`` | ``"explain"`` —
            mirrors the proposal's action.
        created_at: Wall-clock of provenance write (i.e. when the
            user saved the notebook after accepting the proposal).
    """

    __tablename__ = "notebook_cell_provenance"

    __table_args__ = (
        Index(
            "ix_notebook_cell_provenance_cell",
            "cell_uuid",
            "created_at",
        ),
        Index(
            "ix_notebook_cell_provenance_run",
            "agent_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cell_uuid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebook_cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookBranchBinding(Base):
    """Per-notebook Delta-branch binding (Phase 102).

    Lets a notebook declare that its writes target a named Delta
    branch instead of the canonical (``main``) table state.  The
    kernel-side ``pql.read_table`` / ``pql.write_table`` primitives
    read this binding via the env bridge (``POINTLESSQL_BRANCH``)
    so a single ``.py`` runs identically against ``main`` and a
    branch — only the resolved storage layer changes.

    Promotion is a separate step gated by a human review:
    ``promote_branch_for_notebook`` calls the existing
    :func:`pointlessql.services.agent_runs.memory._branch.branch_from_run`
    promotion path with the notebook-bound branch as the source.
    Once promoted the binding's ``promoted_at`` timestamp is set;
    a subsequent edit either creates a fresh binding or discards
    the binding outright.

    History rows stay around — one notebook can have many bindings
    over its lifetime, but only one without a ``superseded_at`` is
    "current".  This matches the Phase-95 cell-identity tombstone
    pattern.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        branch_name: The Delta-branch name (e.g.
            ``"agent_42__exp1"``).  Free-text; the branch service
            (``services/agent_runs/memory/_branch.py``) owns naming.
        base_revision_uuid: Optional Phase-97
            :class:`NotebookRevision` UUID this branch forks from —
            so replay can reproduce the exact starting point.
        created_by_user_id: Audit pointer to the binder.
        created_at: Wall-clock when the binding was minted.
        promoted_at: Set when the branch was promoted to ``main``.
        promoted_by_user_id: Audit pointer to the promoter.
        discarded_at: Set when the binding was rolled back without
            promotion.
        superseded_at: Set when a fresh binding replaced this one.
    """

    __tablename__ = "notebook_branch_bindings"

    __table_args__ = (
        Index(
            "ix_nb_branch_binding_notebook_active",
            "notebook_id",
            "superseded_at",
        ),
        Index("ix_nb_branch_binding_branch", "branch_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_revision_uuid: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    promoted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    discarded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotebookShare(Base):
    """Public-share grant for a notebook (Phase 100).

    One row mints an unguessable v4 UUID under
    ``/share/notebook/{share_uuid}`` so a notebook can be shared
    read-only without authentication.  Two modes:

    * ``snapshot`` *(default — safer)* — freezes the current state
      as a tagged :class:`NotebookRevision`; later in-place edits
      do not leak.  ``revision_uuid`` points at the frozen row.
      Re-publish updates the snapshot under the same share UUID
      (the link stays stable); Unpublish revokes entirely.
    * ``live`` — link always reflects the current ``.py`` +
      last-known outputs.  ``revision_uuid`` is null; the editor
      paints a persistent "LIVE share" badge while active so
      accidental secret-push is obvious.

    A second flag (``dashboard_mode``) toggles between
    "regular notebook" rendering and the dashboard rendering that
    strips code cells and shows only markdown + outputs.

    Attributes:
        id: Auto-incremented primary key.
        share_uuid: 36-char v4 UUID — the URL slug.  Stable across
          re-publish; rotated only on unpublish + republish.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
          the notebook.
        share_mode: ``"snapshot"`` | ``"live"``.
        dashboard_mode: ``True`` when the share should render only
          markdown + outputs (no code).
        revision_uuid: For ``snapshot`` mode — FK-by-uuid to the
          :class:`NotebookRevision` row that is the frozen view.
          ``None`` for ``live``.
        created_by_user_id: Audit pointer.
        created_at: Wall-clock when the share row was minted.
        expires_at: Optional auto-expiry timestamp; ``None`` means
          no expiry.
        revoked_at: Soft-revoke tombstone.  Once set the share UUID
          returns 410 Gone.
    """

    __tablename__ = "notebook_shares"

    __table_args__ = (
        UniqueConstraint("share_uuid", name="uq_notebook_shares_uuid"),
        Index(
            "ix_notebook_shares_notebook_active",
            "notebook_id",
            "revoked_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    share_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    share_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    dashboard_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    revision_uuid: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotebookWidget(Base):
    """Parameter-widget definition attached to a notebook (Phase 99).

    Widgets are interactive controls rendered as a form above the
    notebook — dropdowns / sliders / text inputs.  Each row defines
    one widget; the kernel-side ``pql.widgets`` shim reads the current
    values via the env bridge so a parameterised notebook can drive
    its execution from a form rather than hard-coded constants.

    The widget vocabulary is intentionally small (dropdown / slider /
    text) so the UI stays narrow.  Default values + bounds are
    JSON-encoded so the same row can describe a dropdown's options
    AND a slider's min/max without column proliferation.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        name: Identifier the kernel sees (e.g. ``"region"``).
            Unique per notebook.
        widget_kind: ``"dropdown"`` | ``"slider"`` | ``"text"``.
        label: Human-friendly label rendered above the input.
        config_json: JSON blob with the widget-kind-specific config
            (``options`` for dropdown, ``min`` / ``max`` / ``step``
            for slider, ``placeholder`` for text).
        default_value: Default value as a JSON-encoded scalar.
        position: Display order; smaller is earlier.
        created_at: When the widget was first defined.
        updated_at: Last edit timestamp.
    """

    __tablename__ = "notebook_widgets"

    __table_args__ = (
        UniqueConstraint(
            "notebook_id", "name", name="uq_notebook_widgets_name_per_nb"
        ),
        Index("ix_notebook_widgets_notebook", "notebook_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    widget_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookPermission(Base):
    """Per-notebook share permission (Phase 99).

    Layered on top of workspace membership: a workspace member who
    is not explicitly granted a notebook role still falls back to
    the workspace role (members can view; admins can edit).  This
    table lets a notebook be shared OUTSIDE its workspace's default
    permissioning — granting "view" to a stakeholder who otherwise
    has no edit rights, or upgrading "view" to "run" so a non-editor
    can re-execute cells.

    Roles form a lattice ``view < run < edit``; a higher role
    implicitly grants the lower ones.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        user_id: FK to :class:`User` — the principal the role is
            granted to.
        role: ``"view"`` | ``"run"`` | ``"edit"``.
        granted_by_user_id: Audit pointer to the grantor — usually
            an admin or the notebook owner.
        granted_at: Wall-clock the grant landed.
    """

    __tablename__ = "notebook_permissions"

    __table_args__ = (
        UniqueConstraint(
            "notebook_id", "user_id", name="uq_notebook_perms_per_user"
        ),
        Index("ix_notebook_perms_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookCellSequenceProposal(Base):
    """Multi-cell AI proposal — full code-gen flow (Phase 104).

    Extends the Phase-96 single-cell propose / fix / explain proposals
    to a full sequence: one prompt yields a coherent ``imports →
    DataFrame → plot → markdown`` sequence the user can insert as a
    block.  Each row carries the full cell list as JSON so insertion
    is atomic (no partial accept-then-discard pollution) and the
    reviewer-per-cell flow from Phase 101 can fan out comments to
    each cell individually after acceptance.

    Lifecycle: ``pending`` → ``accepted`` | ``discarded`` |
    ``expired``.  An accepted row fans out to N
    :class:`NotebookCellProvenance` rows once the save-path
    reconciler mints UUIDs for the freshly inserted cells.

    Attributes:
        id: Auto-incremented primary key.
        proposal_id: 36-char stable UUID for REST URLs.
        chat_session_id: FK to :class:`EditorChatSession` — the
            originating turn lives in the chat session.
        prompt: Verbatim user prompt that produced the sequence.
        cells_json: JSON list ``[{position, cell_type, source,
            result_var, tags}, …]`` — the inserted order is
            ``position`` ascending.
        rationale: Optional model-side narrative for the suggestion.
        status: One of :data:`NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES`.
        created_at: Wall-clock at proposal insertion.
        accepted_at: Set when the user accepts.
        accepted_by_user_id: Audit pointer.
        discarded_at: Set when the user discards.
    """

    __tablename__ = "notebook_cell_sequence_proposals"

    __table_args__ = (
        UniqueConstraint(
            "proposal_id", name="uq_nb_cell_sequence_proposal_uuid"
        ),
        Index(
            "ix_nb_cell_sequence_session",
            "chat_session_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chat_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("editor_chat_sessions.id"),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cells_json: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    discarded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


#: Allowed values for :attr:`NotebookCellSequenceProposal.status`.
NOTEBOOK_CELL_SEQUENCE_PROPOSAL_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "discarded",
    "expired",
)


class NotebookReplay(Base):
    """One replay attempt of an old notebook revision (Phase 103).

    The replay surface re-executes a Phase-97 :class:`NotebookRevision`
    against today's data and stores the fresh outputs alongside the
    frozen historical ones, so a reviewer can spot which cells now
    produce different results.  This is the AV-governance
    "shadow mode" pattern applied to notebooks: the original
    revision stays untouched (no chance of overwriting it); the
    replay row is the diff anchor.

    A replay may optionally target a Phase-102 branch instead of
    ``main`` so the re-execution does not corrupt the production
    table — flag stored in ``branch_name``.

    Attributes:
        id: Auto-incremented primary key.
        replay_uuid: 36-char stable identifier for REST URLs.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        base_revision_uuid: Phase-97 revision the replay forks
            from.  Frozen; the replay never edits this row.
        branch_name: Optional Phase-102 branch the replay's writes
            target.  ``None`` means the replay runs read-only or
            against ``main`` (caller's choice).
        status: ``"pending"`` | ``"running"`` | ``"ok"`` |
            ``"error"`` | ``"cancelled"``.
        started_at: When the replay was kicked off.
        finished_at: When the replay reached a terminal state.
        outputs_json: Canonical JSON encoding of the replayed
            outputs once they land.  Empty list until completion.
        diff_summary_json: Optional digest of the cell-by-cell diff
            (``{stable, changed, missing, new}`` counts) so the
            list page can render the comparison without re-running
            the diff.
        triggered_by_user_id: Audit pointer.
    """

    __tablename__ = "notebook_replays"

    __table_args__ = (
        UniqueConstraint("replay_uuid", name="uq_notebook_replays_uuid"),
        Index(
            "ix_notebook_replays_notebook_started",
            "notebook_id",
            "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    replay_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_revision_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    branch_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outputs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    diff_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class NotebookCellAuthorship(Base):
    """Per-cell authorship attribution (Phase 101).

    The Phase-96 :class:`NotebookCellProvenance` table records every
    accepted AI-assistant proposal as an append-only audit log.
    Authorship is the *current* attribution surface: "who minted this
    cell and who last touched it".  Used by the editor's cell-header
    chip ("agent A • last edited by user B") and by the reviewer-per-
    cell flow so a reviewer agent can see at a glance whether the
    cell came from a human or a fellow agent.

    One row per :class:`NotebookCellIdentity.id` (1:1).  The save-path
    reconciler upserts on every save: a brand-new cell gets a fresh
    row marked with the saver's identity; a touched cell bumps
    ``last_modified_at`` and the ``last_modifier_*`` columns without
    overwriting the ``first_*`` history.

    Attributes:
        cell_uuid: PK + FK to :class:`NotebookCellIdentity.id`.
            Cascade-delete so a tombstoned cell loses its attribution
            row too.
        first_author_kind: ``"user"`` or ``"agent"``.
        first_author_email: Email of the human author when
            ``first_author_kind == "user"``.  ``None`` otherwise.
        first_author_agent_id: FK to :class:`Agent` when the cell was
            minted by an agent.  ``None`` for human-authored.
        first_author_agent_run_id: ``agent_runs.id`` snapshot — the
            run context the agent was in when it minted the cell.
            Surfaces in the Phase 103 replay surface.
        last_modifier_kind: Same shape as ``first_author_kind`` —
            tracks the most recent edit author.
        last_modifier_email: As ``first_author_email``.
        last_modifier_agent_id: As ``first_author_agent_id``.
        created_at: When the cell first appeared.
        last_modified_at: When the cell source last changed.
    """

    __tablename__ = "notebook_cell_authorship"

    __table_args__ = (
        Index("ix_cell_authorship_first_agent", "first_author_agent_id"),
        Index("ix_cell_authorship_last_agent", "last_modifier_agent_id"),
    )

    cell_uuid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebook_cells.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_author_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    first_author_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    first_author_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agents.id"), nullable=True
    )
    first_author_agent_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_modifier_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    last_modifier_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    last_modifier_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agents.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookRevision(Base):
    """Save-time snapshot of a notebook's cells + outputs (Phase 97).

    Each row freezes the notebook state at a discrete save event so
    the editor's revision-history panel can render a Monaco diff
    between any two points in time, replay an old execution against
    today's data (Phase 103), or surface the agent timeline alongside
    the human edit timeline (Phase 101).

    The snapshot lives in this metadata DB rather than on the
    on-disk ``.py`` so:

    * The ``.py`` stays IDE-agnostic (the per-feedback rule
      ``feedback_notebook_py_editability``).
    * Outputs travel with the snapshot — re-rendering an old
      revision does not require re-running the kernel.
    * Cell-level diffs use the stable ``content_hash`` identity
      keyed by :class:`NotebookCellIdentity` so cell reordering is
      cheap to detect.

    ``content_sha256`` is a deterministic hash of the canonical JSON
    encoding of ``(cells, outputs)``.  It is the basis for a future
    shoreguard-fresh cryptographic signature (Phase 97 stretch goal;
    deferred until the shoreguard signing API ships).  Two columns
    ride along ready for that integration: ``signature_alg`` (e.g.
    ``"shoreguard-v1"``) and ``signature`` (the opaque blob).  Both
    are nullable today — every snapshot still records its
    deterministic hash, only the signature step is pending.

    Attributes:
        id: Auto-incremented primary key.
        revision_uuid: 36-char UUID4 the editor surfaces in the URL
            and the API; stable across DB exports / imports.
        notebook_id: FK to :class:`Notebook` — cascade-delete so a
            removed notebook drops its revision rows.
        parent_revision_id: FK to self for "this snapshot's parent"
            so the diff viewer can render an ancestry chain.  Null
            on the first revision per notebook.
        created_by: User email; null when written by an agent /
            scheduler with no human author.
        created_at: Wall-clock when the snapshot landed.
        message: Optional save message ("checkpoint before X
            refactor") — keeps the panel readable.
        cells_json: Canonical JSON encoding of the cell list at
            save time; ``[{content_hash, cell_type, source,
            result_var, tags}, …]``.
        outputs_json: Canonical JSON encoding of the latest-session
            output rows at save time.
        content_sha256: SHA-256 hex digest of the canonical JSON
            ``cells_json + outputs_json`` payload.  Stable across
            re-saves of an identical notebook (which then collapse
            into the same revision).
        signature_alg: Future shoreguard signature algorithm
            identifier (``"shoreguard-v1"`` planned).  Null while
            the integration is pending.
        signature: Future shoreguard signature blob.  Null while
            the integration is pending.
    """

    __tablename__ = "notebook_revisions"

    __table_args__ = (
        UniqueConstraint(
            "notebook_id",
            "content_sha256",
            name="uq_notebook_revisions_notebook_sha",
        ),
        Index("ix_notebook_revisions_notebook_created", "notebook_id", "created_at"),
        Index("ix_notebook_revisions_uuid", "revision_uuid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True
    )
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_revision_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("notebook_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cells_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_alg: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotebookTag(Base):
    """Notebook-level lifecycle tags (Phase 98.B).

    Tags categorise a notebook in the workspace tree (``draft`` /
    ``etl`` / ``prod`` / etc.).  Different from
    :data:`pointlessql.services.notebook.cell_tags.CURATED_CELL_TAGS`
    — those tag *cells inside* a notebook via the marker grammar,
    while a :class:`NotebookTag` tags the *notebook itself* so the
    workspace tree can filter by tag.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete so a
            removed notebook drops its tag rows too.
        tag: Lowercase tag string; the route normalises before write.
        created_at: When the tag was attached; surfaces in audit.
    """

    __tablename__ = "notebook_tags"

    __table_args__ = (
        UniqueConstraint(
            "notebook_id",
            "tag",
            name="uq_notebook_tags_notebook_tag",
        ),
        Index("ix_notebook_tags_tag", "tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
