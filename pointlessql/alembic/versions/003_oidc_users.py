"""Add OIDC identity columns to users table.

Revision ID: 003
Revises: 002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make password_hash nullable and add oidc_provider/oidc_subject."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(128),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("oidc_provider", sa.String(500), nullable=True),
        )
        batch_op.add_column(
            sa.Column("oidc_subject", sa.String(500), nullable=True),
        )

    # Partial unique index — only constrains rows that have an OIDC identity.
    op.execute(
        "CREATE UNIQUE INDEX ix_users_oidc_identity "
        "ON users (oidc_provider, oidc_subject) "
        "WHERE oidc_provider IS NOT NULL"
    )


def downgrade() -> None:
    """Remove OIDC columns and restore password_hash NOT NULL."""
    op.drop_index("ix_users_oidc_identity", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("oidc_subject")
        batch_op.drop_column("oidc_provider")
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(128),
            nullable=False,
        )
