"""Save-time revision snapshots + pinned facts.

Two related tables: every save event freezes a ``NotebookRevision``
that the diff viewer + replay surface read; a long-lived bookmark on
a revision (whole or one cell's output) becomes a ``NotebookRevisionFact``
in the workspace's library.
"""

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


class NotebookRevision(Base):
    """Save-time snapshot of a notebook's cells + outputs.

    Each row freezes the notebook state at a discrete save event so
    the editor's revision-history panel can render a Monaco diff
    between any two points in time, replay an old execution against
    today's data, or surface the agent timeline alongside
    the human edit timeline.

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
    revision_uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
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


class NotebookRevisionFact(Base):
    """Pinned snapshot promoted into a referenceable fact.

    A *fact* is a long-lived bookmark on a :class:`NotebookRevision` —
    either the whole revision (``cell_content_hash IS NULL``) or one
    specific cell's frozen output inside it (``cell_content_hash``
    pins down which cell).  Facts add the human-readable shape
    (``title`` + ``description_md``) on top of the deterministic hash
    already living on the revision row so the workspace's
    ``/library/facts`` browse surface reads like a curated answer list
    rather than a raw audit log.

    Soft-delete via ``unpinned_at`` keeps the audit trail intact: an
    unpinned fact stays in the row history (analyst can see *why* it
    is gone) while disappearing from the active list.  The partial
    UNIQUE on ``(workspace_id, revision_id, cell_content_hash)``
    filtered to ``unpinned_at IS NULL`` makes ``pin`` idempotent
    without re-using a soft-deleted row's slot.

    Attributes:
        id: Auto-incremented primary key.
        fact_uuid: 36-char UUID4 surfaced in REST URLs; stable across
            DB exports / imports.
        workspace_id: Tenant scope — facts pinned in one workspace are
            invisible to another even when the underlying revision is
            shared.
        social_target_id: FK to :class:`SocialTarget` — the polymorphic
            anchor for Phase-81 followers / feed.  ``entity_kind`` is
            ``'notebook_revision'`` for whole-revision facts or
            ``'notebook_cell_output'`` for per-cell-output facts.
        revision_id: FK to :class:`NotebookRevision`.  Cascade-delete
            so removing a revision drops its facts (rare — revisions
            are append-only) without leaving dangling rows.
        cell_content_hash: When set, the fact pins one specific cell's
            output inside the revision (Phase-98.C cell-lineage chip's
            sibling primitive).  ``NULL`` pins the whole revision.
        title: Human-readable label (≤ 200 chars).  Required.
        description_md: Optional Markdown description rendered on the
            library card + fact detail page.
        result_snapshot_json: Optional frozen JSON snapshot of the
            cell's last-known output frame (columns + preview rows),
            mirroring :class:`LensPinnedAnswer.result_preview`.
            ``NULL`` for whole-revision facts.
        pinned_by_user_id: FK to ``users.id``; ``NULL`` for agent-
            driven pins.
        pinned_by_agent_id: ``agent_id`` string when the pin came from
            an agent run via :func:`pql.facts.pin`; ``NULL`` for
            human-driven pins.  Mutually exclusive with
            ``pinned_by_user_id`` only by convention — service-layer
            validation enforces that at least one is set.
        pinned_at: Wall-clock when the pin landed.
        unpinned_at: Wall-clock soft-delete marker; ``NULL`` while
            active.  An unpinned fact stays in the row history for the
            audit trail and the library hides it from the default list.
    """

    __tablename__ = "notebook_revision_facts"

    __table_args__ = (
        # Idempotent pin: same (workspace, revision, cell_content_hash)
        # collapses while the fact is active.  The partial filter on
        # ``unpinned_at IS NULL`` lets a re-pin after an unpin mint a
        # fresh row rather than resurrecting the old one (which would
        # confuse soft-delete semantics).  SQLite + Postgres both
        # support partial UNIQUE; the Alembic migration spells it via
        # ``op.create_index`` with ``unique=True`` + ``postgresql_where``.
        Index(
            "uq_notebook_revision_facts_active",
            "workspace_id",
            "revision_id",
            "cell_content_hash",
            unique=True,
            sqlite_where=text("unpinned_at IS NULL"),
            postgresql_where=text("unpinned_at IS NULL"),
        ),
        Index(
            "ix_notebook_revision_facts_workspace_pinned",
            "workspace_id",
            "pinned_at",
        ),
        Index(
            "ix_notebook_revision_facts_revision",
            "revision_id",
        ),
        Index(
            "ix_notebook_revision_facts_uuid",
            "fact_uuid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fact_uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False)
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("notebook_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    cell_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    pinned_by_agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pinned_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    unpinned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
