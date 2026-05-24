"""phase77.7 — GitHub-Issues entity (issues + labels + milestones).

Issues are the long-form "tracked work item" primitive sitting
alongside the freeform polymorphic Discussion thread.  The split
mirrors GitHub's split between Issues and Discussions: a comment
is ephemeral chat; an issue carries state, assignee, labels and a
milestone.  An issue against a table / model / branch / DP gets
its own ``social_targets`` row (``kind='issue'``) so the issue is
itself comment-able, follow-able, star-able and endorsement-able
(self-similarity).

Three tables:

* ``issues`` — one row per opened issue.  ``social_target_id`` is
  the issue's own anchor row; ``parent_social_target_id`` points
  back at the parent entity (table/model/branch/dp).  Both FKs
  carry ``ondelete=CASCADE`` so deleting the parent or the anchor
  cleans up the issue row.  ``labels_json`` is a JSON array of
  label slugs (TEXT) — labels are slugs, fast to read.  No M:N
  junction; per locked decision in the Phase-77 plan,
  filtering-by-label goes through 77.9 FTS or client-side.
* ``issue_labels`` — workspace-scoped label catalogue.  Slugs are
  unique per workspace.
* ``issue_milestones`` — workspace-scoped milestone catalogue.
  An issue carries at most one milestone (mirrors GitHub).

Two CHECK constraints on ``issues``:

* ``state`` must be one of ``open`` / ``closed`` /
  ``closed_not_planned``.
* ``closed_reason`` is ``NULL`` or one of ``fixed`` /
  ``wont_fix`` / ``duplicate`` / ``superseded``.

Three indexes on ``issues``:

* ``(workspace_id, state)`` — index lane for the "open issues
  across the workspace" listing.
* ``parent_social_target_id`` — supports "issues opened against
  this entity" tabs on detail pages.
* ``assignee_user_id`` — supports the "issues assigned to me"
  profile-tab query in 77.10.

No new ``entity_kind`` row needed on ``social_targets`` — the
kind whitelist CHECK constraint already permits ``'issue'``
(landed in Phase 77.0).

Revision ID: e2g4i6k8m0o2
Revises: d1g3i5k7m9o1
Create Date: 2026-05-15 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2g4i6k8m0o2"
down_revision: str | None = "d1g3i5k7m9o1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the issues + issue_labels + issue_milestones tables."""
    # ──────────────────────────────────────────────────────────────
    # issue_milestones — referenced by FK from issues, so create first.
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "issue_milestones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_issue_milestones_workspace",
        "issue_milestones",
        ["workspace_id"],
    )

    # ──────────────────────────────────────────────────────────────
    # issue_labels — workspace-scoped label catalogue.
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "issue_labels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("label_text", sa.String(80), nullable=False),
        sa.Column(
            "color_hex",
            sa.String(7),
            nullable=False,
            server_default="#cccccc",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_issue_labels_slug_per_workspace"),
    )

    # ──────────────────────────────────────────────────────────────
    # issues — the primary table.  Two CASCADE FKs to social_targets
    # so the issue cleans up when the anchor or the parent goes away.
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "state",
            sa.String(20),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "assignee_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "opened_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(20), nullable=True),
        sa.Column(
            "milestone_id",
            sa.Integer(),
            sa.ForeignKey("issue_milestones.id"),
            nullable=True,
        ),
        sa.Column(
            "labels_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.UniqueConstraint("social_target_id", name="uq_issues_social_target"),
        sa.CheckConstraint(
            "state IN ('open', 'closed', 'closed_not_planned')",
            name="ck_issues_state",
        ),
        sa.CheckConstraint(
            "closed_reason IS NULL OR closed_reason IN ("
            "'fixed', 'wont_fix', 'duplicate', 'superseded'"
            ")",
            name="ck_issues_closed_reason",
        ),
    )
    op.create_index(
        "ix_issues_workspace_state",
        "issues",
        ["workspace_id", "state"],
    )
    op.create_index(
        "ix_issues_parent",
        "issues",
        ["parent_social_target_id"],
    )
    op.create_index(
        "ix_issues_assignee",
        "issues",
        ["assignee_user_id"],
    )


def downgrade() -> None:
    """Drop issues + issue_labels + issue_milestones in reverse order."""
    op.drop_index("ix_issues_assignee", table_name="issues")
    op.drop_index("ix_issues_parent", table_name="issues")
    op.drop_index("ix_issues_workspace_state", table_name="issues")
    op.drop_table("issues")
    op.drop_table("issue_labels")
    op.drop_index("ix_issue_milestones_workspace", table_name="issue_milestones")
    op.drop_table("issue_milestones")
