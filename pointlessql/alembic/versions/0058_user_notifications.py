"""user notifications + digest opt-in

Adds the ``user_notifications`` per-recipient inbox table backing
``/notifications`` + ``GET /api/notifications`` (Phase 71.4), and
extends ``users`` with ``digest_email_optin`` for the daily
marketplace-digest opt-in.

The new column carries a server-side default of ``false`` so
existing rows backfill without an explicit UPDATE.

Revision ID: 0058
Revises: 0057
Create Date: 2026-05-12 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``user_notifications`` + add ``users.digest_email_optin``."""
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "recipient_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "source_data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_user_notif_recipient_unread",
        "user_notifications",
        ["recipient_user_id", "read_at"],
    )
    op.create_index(
        "ix_user_notif_recipient_created",
        "user_notifications",
        ["recipient_user_id", "created_at"],
    )

    op.add_column(
        "users",
        sa.Column(
            "digest_email_optin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop ``user_notifications`` + remove ``users.digest_email_optin``."""
    op.drop_column("users", "digest_email_optin")
    op.drop_index("ix_user_notif_recipient_created", table_name="user_notifications")
    op.drop_index("ix_user_notif_recipient_unread", table_name="user_notifications")
    op.drop_table("user_notifications")
