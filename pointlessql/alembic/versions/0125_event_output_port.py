"""event-stream output-port substrate (B1/D1)

Adds two tables that back the runtime of declared ``kind='event'``
output ports:

- ``data_product_event_subscriptions``  durable consumer subscriptions
  (one per consumer, tracks a Delta-CDF position cursor).
- ``data_product_event_deliveries``     per-pump audit row (small,
  TTL-pruned).

CASCADE on ``data_products.id`` and on
``data_product_output_ports.id`` so an output-port removal cleans up
the subscriptions to it.

The actual streaming runtime (WS hub + scheduler pump + the
``GET .../events`` chunked endpoint) is opt-in via
:class:`pointlessql.config.EventPortSettings` and is **default-OFF**
even after this migration applies — flipping the flag without
declared ``kind='event'`` rows still does nothing.

Revision ID: 0125
Revises: 0124
Create Date: 2026-05-30 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0125"
down_revision: str | None = "0124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the subscription + delivery tables."""
    op.create_table(
        "data_product_event_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "output_port_id",
            sa.Integer(),
            sa.ForeignKey("data_product_output_ports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=200), nullable=False),
        sa.Column("consumer_label", sa.String(length=120), nullable=False),
        sa.Column(
            "position_marker_json",
            sa.Text(),
            nullable=False,
            server_default='{"version": 0, "row_offset": 0}',
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "output_port_id",
            "consumer_label",
            "table_name",
            name="uq_dp_event_subs_identity",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','closed')",
            name="ck_dp_event_subs_status",
        ),
    )
    op.create_index(
        "ix_dp_event_subs_product",
        "data_product_event_subscriptions",
        ["data_product_id"],
    )
    op.create_index(
        "ix_dp_event_subs_status",
        "data_product_event_subscriptions",
        ["status"],
    )

    op.create_table(
        "data_product_event_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("data_product_event_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_from", sa.Integer(), nullable=False),
        sa.Column("version_to", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok','error','empty')",
            name="ck_dp_event_deliveries_status",
        ),
    )
    op.create_index(
        "ix_dp_event_deliveries_subscription",
        "data_product_event_deliveries",
        ["subscription_id", "delivered_at"],
    )


def downgrade() -> None:
    """Drop the subscription + delivery tables."""
    op.drop_index(
        "ix_dp_event_deliveries_subscription",
        table_name="data_product_event_deliveries",
    )
    op.drop_table("data_product_event_deliveries")
    op.drop_index(
        "ix_dp_event_subs_status",
        table_name="data_product_event_subscriptions",
    )
    op.drop_index(
        "ix_dp_event_subs_product",
        table_name="data_product_event_subscriptions",
    )
    op.drop_table("data_product_event_subscriptions")
