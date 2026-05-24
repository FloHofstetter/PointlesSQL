"""Per-notebook Delta-branch binding.

Lets a notebook declare that its writes target a named Delta branch
instead of the canonical (``main``) table state.  History rows stay
around so a single notebook can have many bindings over its lifetime.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookBranchBinding(Base):
    """Per-notebook Delta-branch binding.

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
    base_revision_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
