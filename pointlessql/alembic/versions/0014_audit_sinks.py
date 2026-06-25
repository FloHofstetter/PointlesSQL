"""audit_sinks + governance_events tables

's first sub-sprint extends the existing CloudEvent
emission catalog with six new governance event types and adds a
pluggable sink-type fan-out so an organisation can route the same
envelope at multiple destinations (webhook + S3 + AWS CloudTrail).

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_sinks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("event_types_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('webhook','s3','aws_cloudtrail')",
            name="ck_audit_sinks_type",
        ),
        sa.UniqueConstraint("name", name="uq_audit_sinks_name"),
    )
    op.create_index("ix_audit_sinks_active", "audit_sinks", ["is_active"])

    op.create_table(
        "governance_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("delivered_to_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('pending','delivered','delivery_failed','no_destination')",
            name="ck_governance_events_outcome",
        ),
    )
    op.create_index(
        "ix_governance_events_fired",
        "governance_events",
        ["event_type", "fired_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_governance_events_fired", table_name="governance_events")
    op.drop_table("governance_events")
    op.drop_index("ix_audit_sinks_active", table_name="audit_sinks")
    op.drop_table("audit_sinks")
