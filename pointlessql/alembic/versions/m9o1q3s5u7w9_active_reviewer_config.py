"""data product active reviewer config (Phase 74.0)

Adds the ``data_product_active_reviewer_configs`` table backing
the Phase-74 active-reviewer surface.  One row per
``(workspace, dp)``; the row carries the runner selection (in-proc
loop vs Hermes-cron), the LLM provider + model overrides for the
in-proc path, an optional prompt-override, and the
``last_run_at`` + ``last_run_comment_id`` pointers stamped by the
service.

Revision ID: m9o1q3s5u7w9
Revises: l8n0p2r4t6v8
Create Date: 2026-05-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m9o1q3s5u7w9"
down_revision: str | None = "l8n0p2r4t6v8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_active_reviewer_configs``."""
    op.create_table(
        "data_product_active_reviewer_configs",
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
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("runner", sa.String(length=20), nullable=False),
        sa.Column("llm_provider", sa.String(length=20), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("prompt_override_md", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_run_comment_id",
            sa.Integer(),
            sa.ForeignKey("data_product_comments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "acting_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            name="uq_dp_active_reviewer_cfg",
        ),
        sa.CheckConstraint(
            "runner IN ('inproc', 'hermes_cron')",
            name="ck_dp_active_reviewer_runner",
        ),
        sa.CheckConstraint(
            "(llm_provider IS NULL) OR (llm_provider IN ('anthropic', 'openai'))",
            name="ck_dp_active_reviewer_provider",
        ),
    )


def downgrade() -> None:
    """Drop ``data_product_active_reviewer_configs``."""
    op.drop_table("data_product_active_reviewer_configs")
