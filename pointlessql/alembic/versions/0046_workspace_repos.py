"""workspace_repos + workspace_repo_secrets for git-backed workspaces

Phase 51.1 introduces the cache shape behind git-backed
workspaces.  Two tables, one migration:

* ``workspace_repos`` — one row per (workspace, slug) pinning a
  remote URL + tracked branch + provider kind + sync state.
* ``workspace_repo_secrets`` — encrypted auth credentials.  Plain
  text is encrypted via the ``Fernet`` master key in
  ``system_keys`` before insert; never landed at rest.

Every workspace_id FK carries ``server_default='1'`` matching the
Phase-29 backfill convention.

Revision ID: 0046
Revises: 0045
Create Date: 2026-05-07 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workspace_repos + workspace_repo_secrets."""
    op.create_table(
        "workspace_repos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column(
            "default_branch",
            sa.String(length=120),
            nullable=False,
            server_default="main",
        ),
        sa.Column(
            "provider_kind",
            sa.String(length=32),
            nullable=False,
            server_default="generic",
        ),
        sa.Column(
            "sync_state",
            sa.String(length=16),
            nullable=False,
            server_default="idle",
        ),
        sa.Column("last_synced_sha", sa.String(length=40), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "slug",
            name="uq_workspace_repos_workspace_slug",
        ),
    )
    with op.batch_alter_table("workspace_repos", schema=None) as batch_op:
        batch_op.create_index(
            "ix_workspace_repos_workspace_synced",
            ["workspace_id", "last_synced_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_workspace_repos_state",
            ["sync_state"],
            unique=False,
        )

    op.create_table(
        "workspace_repo_secrets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_repo_id",
            sa.Integer(),
            sa.ForeignKey("workspace_repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_repo_id",
            "kind",
            name="uq_workspace_repo_secrets_repo_kind",
        ),
    )
    with op.batch_alter_table("workspace_repo_secrets", schema=None) as batch_op:
        batch_op.create_index(
            "ix_workspace_repo_secrets_repo",
            ["workspace_repo_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop workspace_repo_secrets + workspace_repos."""
    with op.batch_alter_table("workspace_repo_secrets", schema=None) as batch_op:
        batch_op.drop_index("ix_workspace_repo_secrets_repo")
    op.drop_table("workspace_repo_secrets")
    with op.batch_alter_table("workspace_repos", schema=None) as batch_op:
        batch_op.drop_index("ix_workspace_repos_state")
        batch_op.drop_index("ix_workspace_repos_workspace_synced")
    op.drop_table("workspace_repos")
