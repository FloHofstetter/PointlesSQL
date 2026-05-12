"""user webhook subscriptions (Phase 72.6)

Adds the ``user_webhook_subscriptions`` table backing per-user
CloudEvent webhook subscriptions.  Subscriptions filter by
``event_type_filter`` (exact or ``"*"`` wildcard) +
``dp_ref_filter`` (optional ``"catalog.schema"``); the
``hmac_secret`` is generated server-side at create time and
returned to the caller once.

Revision ID: h4j6l8n0p2r4
Revises: g3i5k7m9o1q3
Create Date: 2026-05-13 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h4j6l8n0p2r4"
down_revision: str | None = "g3i5k7m9o1q3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``user_webhook_subscriptions``."""
    op.create_table(
        "user_webhook_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("webhook_url", sa.String(length=1000), nullable=False),
        sa.Column("hmac_secret", sa.String(length=128), nullable=False),
        sa.Column("event_type_filter", sa.String(length=120), nullable=False),
        sa.Column("dp_ref_filter", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_delivered_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_user_webhook_sub_user_active",
        "user_webhook_subscriptions",
        ["user_id", "is_active"],
    )
    op.create_index(
        "ix_user_webhook_sub_event_type",
        "user_webhook_subscriptions",
        ["event_type_filter"],
    )


def downgrade() -> None:
    """Drop ``user_webhook_subscriptions``."""
    op.drop_index(
        "ix_user_webhook_sub_event_type",
        table_name="user_webhook_subscriptions",
    )
    op.drop_index(
        "ix_user_webhook_sub_user_active",
        table_name="user_webhook_subscriptions",
    )
    op.drop_table("user_webhook_subscriptions")
