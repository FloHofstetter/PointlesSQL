"""feed read markers (seen-cursor)

Adds ``feed_read_markers`` — one row per ``(user, workspace)`` holding a
single ``seen_at`` high-water timestamp.  Rows in the ambient feed
stream created after the cursor are "new"; advancing the cursor is what
lets the infinite stream read as "you're all caught up" without marking
every ambient row read or destroying any history below the line.

Revision ID: 0143
Revises: 0142
Create Date: 2026-06-02 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0143"
down_revision: str | None = "0142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create feed_read_markers with a per-(user, workspace) unique key."""
    op.create_table(
        "feed_read_markers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_feed_read_markers_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_feed_read_markers_workspace",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feed_read_markers"),
        sa.UniqueConstraint(
            "user_id",
            "workspace_id",
            name="uq_feed_read_marker_user_ws",
        ),
    )


def downgrade() -> None:
    """Drop feed_read_markers."""
    op.drop_table("feed_read_markers")
