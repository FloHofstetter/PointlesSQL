"""Create users table.

Revision ID: 001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the users table."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    """Drop the users table."""
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
