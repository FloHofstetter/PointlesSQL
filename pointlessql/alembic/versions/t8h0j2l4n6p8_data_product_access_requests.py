"""data_product_access_requests — self-service access ledger

Adds ``data_product_access_requests`` — one row per consumer request
for SELECT access to a data product.  PointlesSQL records the request
in its own metadata DB and, on a steward / admin approval, issues the
real grant through the soyuz client (never writing lakehouse
permissions directly).

A partial unique index on ``(data_product_id, requester_user_id)``
while ``status='pending'`` keeps a consumer from stacking duplicate open
requests; a decided request is exempt so they can re-request later.

Revision ID: t8h0j2l4n6p8
Revises: s7g9i1k3m5o7
Create Date: 2026-06-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t8h0j2l4n6p8"
down_revision: str | None = "s7g9i1k3m5o7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create data_product_access_requests + its indexes."""
    op.create_table(
        "data_product_access_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_dp_access_request_workspace",
                ondelete="CASCADE",
            ),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey(
                "data_products.id",
                name="fk_dp_access_request_product",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "requester_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_dp_access_request_requester"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decided_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", name="fk_dp_access_request_decider"),
            nullable=True,
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied')",
            name="ck_dp_access_request_status",
        ),
    )
    op.create_index(
        "uq_dp_access_request_open",
        "data_product_access_requests",
        ["data_product_id", "requester_user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_dp_access_request_ws_status",
        "data_product_access_requests",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop data_product_access_requests + its indexes."""
    op.drop_index(
        "ix_dp_access_request_ws_status", table_name="data_product_access_requests"
    )
    op.drop_index("uq_dp_access_request_open", table_name="data_product_access_requests")
    op.drop_table("data_product_access_requests")
