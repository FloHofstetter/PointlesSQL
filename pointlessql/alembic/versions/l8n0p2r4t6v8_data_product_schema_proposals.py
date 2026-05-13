"""data product schema proposals (Phase 73.3)

Adds the ``data_product_schema_proposals`` table backing the
typed schema-change proposal flow.  Both human and agent
authors are supported via a row-level CHECK that requires at
least one of ``proposer_user_id`` / ``proposer_agent_run_id``.

Revision ID: l8n0p2r4t6v8
Revises: k7m9o1q3s5u7
Create Date: 2026-05-14 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l8n0p2r4t6v8"
down_revision: str | None = "k7m9o1q3s5u7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_schema_proposals``."""
    op.create_table(
        "data_product_schema_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "proposer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "proposer_agent_run_id",
            sa.String(length=64),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("diff_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("summary_md", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(length=40), nullable=False, server_default="open"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("resolution_note_md", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'approved_inplace', 'approved_draft', "
            "'rejected')",
            name="ck_dp_proposal_status",
        ),
        sa.CheckConstraint(
            "(proposer_user_id IS NOT NULL) OR "
            "(proposer_agent_run_id IS NOT NULL)",
            name="ck_dp_proposal_proposer_present",
        ),
    )
    op.create_index(
        "ix_dp_proposal_ws_status",
        "data_product_schema_proposals",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_dp_proposal_dp_status",
        "data_product_schema_proposals",
        ["data_product_id", "status"],
    )


def downgrade() -> None:
    """Drop ``data_product_schema_proposals``."""
    op.drop_index(
        "ix_dp_proposal_dp_status",
        table_name="data_product_schema_proposals",
    )
    op.drop_index(
        "ix_dp_proposal_ws_status",
        table_name="data_product_schema_proposals",
    )
    op.drop_table("data_product_schema_proposals")
