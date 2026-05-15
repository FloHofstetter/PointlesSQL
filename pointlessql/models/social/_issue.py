"""GitHub-Issues entity (Phase 77.7).

Issues are the long-form tracked-work primitive, distinct from
the polymorphic Discussion thread.  The split mirrors GitHub:
freeform comments stay in the polymorphic comment table; issues
carry state, assignee, labels, milestone, and a close reason.

An issue itself addresses a ``social_targets`` row
(``kind='issue'``) so the issue is comment-able, follow-able,
star-able and endorsement-able (self-similarity).  A second
``social_target`` FK — ``parent_social_target_id`` — points back
at the entity the issue is opened against (table / model / branch
/ dp).  Both FKs cascade-delete so the row cleans up when either
the anchor or the parent goes away.

Labels live as a JSON array of slugs inside ``labels_json``.  No
M:N junction — per the Phase-77 plan, indexed label filtering
goes through the 77.9 FTS path; for the typical workspace label
count, a junction was not worth the surface.

State + close-reason CHECKs are enforced at the DB layer so a
sloppy PATCH cannot land an out-of-vocabulary value.  The
service-layer parses + writes through SQLAlchemy ORM; raw SQL
should not be needed.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
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

ISSUE_STATES: tuple[str, ...] = ("open", "closed", "closed_not_planned")
ISSUE_CLOSED_REASONS: tuple[str, ...] = (
    "fixed",
    "wont_fix",
    "duplicate",
    "superseded",
)


class Issue(Base):
    """One tracked issue against a platform entity.

    Attributes:
        id: Auto-incremented primary key.  Exposed as the
            ``entity_ref`` of the issue's own ``social_targets``
            row (``kind='issue', entity_ref=str(issue.id)``).
        workspace_id: Tenant scope.
        social_target_id: FK to the issue's own anchor row; unique
            because each issue has exactly one anchor.
            ``ondelete=CASCADE`` so deleting the anchor cleans up
            the issue.
        parent_social_target_id: FK to the parent entity's anchor
            row.  ``ondelete=CASCADE`` so deleting the parent's
            anchor cleans up the issue.
        title: Headline (max 255 chars).  Cannot be empty.
        body_md: Long-form markdown body.  Defaults to empty
            string so an issue can be opened with title-only.
        state: One of :data:`ISSUE_STATES`.  Defaults to ``open``.
        assignee_user_id: Optional FK to the assigned user.
            ``None`` for unassigned issues.
        opened_by_user_id: FK to the user who opened the issue;
            never NULL.
        opened_at: Wall-clock when the issue was opened.
        closed_at: Wall-clock when the issue was closed; ``None``
            while still open.
        closed_reason: One of :data:`ISSUE_CLOSED_REASONS` when
            ``state`` is closed; ``None`` otherwise.
        milestone_id: Optional FK to a milestone (at most one per
            issue, mirrors GitHub).
        labels_json: JSON-encoded array of label slugs; defaults
            to ``'[]'``.  Filtering by label goes through 77.9
            FTS or client-side — no SQL-indexed label lookup.
    """

    __tablename__ = "issues"

    __table_args__ = (
        UniqueConstraint(
            "social_target_id", name="uq_issues_social_target"
        ),
        CheckConstraint(
            "state IN ('open', 'closed', 'closed_not_planned')",
            name="ck_issues_state",
        ),
        CheckConstraint(
            "closed_reason IS NULL OR closed_reason IN ("
            "'fixed', 'wont_fix', 'duplicate', 'superseded'"
            ")",
            name="ck_issues_closed_reason",
        ),
        Index(
            "ix_issues_workspace_state", "workspace_id", "state"
        ),
        Index("ix_issues_parent", "parent_social_target_id"),
        Index("ix_issues_assignee", "assignee_user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_md: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open"
    )
    assignee_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    opened_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    opened_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    closed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_reason: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    milestone_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("issue_milestones.id"), nullable=True
    )
    labels_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="[]"
    )
