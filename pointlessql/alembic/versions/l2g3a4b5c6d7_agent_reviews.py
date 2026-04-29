"""agent_reviews + review_destinations tables (Sprint 19.2.1)

Sprint 19.2.1 makes the daily Audit-Reviewer-Agent's Markdown digest
queryable from inside PointlesSQL itself: every successful review is
persisted into ``agent_reviews`` (severity + summary_md + replay
payload + dispatcher fan-out log), and every active webhook in
``review_destinations`` receives a CloudEvent fan-out that mirrors
the saved-query alert envelope.

Two independent tables, no FK between them — destinations are
admin-configured separately from the per-run review rows.

Revision ID: l2g3a4b5c6d7
Revises: k1f2a3b4c5d6
Create Date: 2026-04-29 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l2g3a4b5c6d7"
down_revision: str | None = "k1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("delivered_to_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('ok','warn','critical')",
            name="ck_agent_reviews_severity",
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="ck_agent_reviews_period",
        ),
    )
    op.create_index(
        "ix_agent_reviews_period_end",
        "agent_reviews",
        ["period_end"],
    )
    op.create_index(
        "ix_agent_reviews_severity",
        "agent_reviews",
        ["severity"],
    )

    op.create_table(
        "review_destinations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("webhook_url", sa.String(length=2000), nullable=False),
        sa.Column("hmac_secret", sa.String(length=256), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "min_severity",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'warn'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "min_severity IN ('ok','warn','critical')",
            name="ck_review_destinations_min_severity",
        ),
        sa.UniqueConstraint("name", name="uq_review_destinations_name"),
    )
    op.create_index(
        "ix_review_destinations_active",
        "review_destinations",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_destinations_active", table_name="review_destinations")
    op.drop_table("review_destinations")
    op.drop_index("ix_agent_reviews_severity", table_name="agent_reviews")
    op.drop_index("ix_agent_reviews_period_end", table_name="agent_reviews")
    op.drop_table("agent_reviews")
