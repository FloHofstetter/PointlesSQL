"""Notebook replay attempts.

The replay surface re-executes a :class:`NotebookRevision`
against today's data and stores the fresh outputs alongside the frozen
historical ones — the AV-governance "shadow mode" pattern applied to
notebooks.
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


class NotebookReplay(Base):
    """One replay attempt of an old notebook revision.

    The replay surface re-executes a :class:`NotebookRevision`
    against today's data and stores the fresh outputs alongside the
    frozen historical ones, so a reviewer can spot which cells now
    produce different results.  This is the AV-governance
    "shadow mode" pattern applied to notebooks: the original
    revision stays untouched (no chance of overwriting it); the
    replay row is the diff anchor.

    A replay may optionally target a branch instead of
    ``main`` so the re-execution does not corrupt the production
    table — flag stored in ``branch_name``.

    Attributes:
        id: Auto-incremented primary key.
        replay_uuid: 36-char stable identifier for REST URLs.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        base_revision_uuid: Revision the replay forks
            from.  Frozen; the replay never edits this row.
        branch_name: Optional branch the replay's writes
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
