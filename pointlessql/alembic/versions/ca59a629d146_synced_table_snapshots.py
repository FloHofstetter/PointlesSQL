"""synced_table_snapshots

Adds the management registry for git-style snapshots / branches of a
synced table's serving copy.  One row per named snapshot, capturing the
Delta version + row count the mirror held at snapshot time plus the
active / promoted / discarded lifecycle; the copy-on-write storage
engine that would back a real branch stays out of scope.

Revision ID: ca59a629d146
Revises: 1f8b223fe7a9
Create Date: 2026-06-20 23:30:16.629383
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ca59a629d146"
down_revision: str | None = "1f8b223fe7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``synced_table_snapshots`` registry table + index."""
    op.create_table(
        "synced_table_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("synced_table_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=True),
        sa.Column("rows_snapshot", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'promoted', 'discarded')",
            name="ck_synced_table_snapshots_status",
        ),
        sa.ForeignKeyConstraint(["synced_table_id"], ["synced_tables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("synced_table_id", "name", name="uq_synced_table_snapshots_table_name"),
    )
    with op.batch_alter_table("synced_table_snapshots", schema=None) as batch_op:
        batch_op.create_index("ix_synced_table_snapshots_table", ["synced_table_id"], unique=False)


def downgrade() -> None:
    """Drop the ``synced_table_snapshots`` table."""
    with op.batch_alter_table("synced_table_snapshots", schema=None) as batch_op:
        batch_op.drop_index("ix_synced_table_snapshots_table")
    op.drop_table("synced_table_snapshots")
