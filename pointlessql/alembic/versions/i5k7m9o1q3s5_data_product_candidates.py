"""data product promotion candidates + yaml drafts (Phase 73.1)

Adds two tables backing the agent-authored data-product flow:

* ``data_product_candidates`` — promote-to-DP suggestion cache,
  refreshed by ``_data_product_promotion_loop``.
* ``data_product_yaml_drafts`` — tracks yaml drafts authored by
  Phase-73 surfaces (candidate-generate, pql.contract, agent
  proposal).

Revision ID: i5k7m9o1q3s5
Revises: h4j6l8n0p2r4
Create Date: 2026-05-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i5k7m9o1q3s5"
down_revision: str | None = "h4j6l8n0p2r4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_candidates`` + ``data_product_yaml_drafts``."""
    op.create_table(
        "data_product_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("catalog_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("table_signature_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distinct_run_count", sa.Integer(), nullable=False),
        sa.Column("write_op_count", sa.Integer(), nullable=False),
        sa.Column("distinct_table_count", sa.Integer(), nullable=False),
        sa.Column("sample_target_table", sa.String(length=767), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="open"
        ),
        sa.Column(
            "dismissed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "promoted_to_data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            name="uq_dp_candidate_target",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'dismissed', 'promoted')",
            name="ck_dp_candidate_status",
        ),
    )
    op.create_index(
        "ix_dp_candidate_ws_status",
        "data_product_candidates",
        ["workspace_id", "status"],
    )

    op.create_table(
        "data_product_yaml_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("catalog_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("draft_path", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_by_agent_run_id",
            sa.String(length=64),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "promoted_to_data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("yaml_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            "yaml_hash",
            name="uq_dp_yaml_draft_content",
        ),
        sa.CheckConstraint(
            "source_kind IN ('candidate_generate', 'pql_contract', "
            "'agent_proposal')",
            name="ck_dp_yaml_draft_source",
        ),
    )
    op.create_index(
        "ix_dp_yaml_draft_ws_open",
        "data_product_yaml_drafts",
        ["workspace_id", "catalog_name", "schema_name"],
    )


def downgrade() -> None:
    """Drop both tables."""
    op.drop_index(
        "ix_dp_yaml_draft_ws_open", table_name="data_product_yaml_drafts"
    )
    op.drop_table("data_product_yaml_drafts")
    op.drop_index(
        "ix_dp_candidate_ws_status", table_name="data_product_candidates"
    )
    op.drop_table("data_product_candidates")
