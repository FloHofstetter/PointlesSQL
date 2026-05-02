"""branch_audit_log table

PointlesSQL-side append-only record of every branch life-cycle event
(create / promote / discard / auto_cleanup).  Survives the discard
of the underlying UC schema so auditors can reconstruct branch
history weeks later.

Revision ID: o5k7m9p2r4t6
Revises: n4i5j6k7l8m9
Create Date: 2026-04-29 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o5k7m9p2r4t6"
down_revision: str | None = "n4i5j6k7l8m9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "branch_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("branch_schema_fqn", sa.String(length=512), nullable=False),
        sa.Column("parent_schema_fqn", sa.String(length=512), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_branch_audit_log_branch_schema_fqn",
        "branch_audit_log",
        ["branch_schema_fqn"],
    )
    op.create_index(
        "ix_branch_audit_log_parent_schema_fqn",
        "branch_audit_log",
        ["parent_schema_fqn"],
    )
    op.create_index(
        "ix_branch_audit_log_run_id",
        "branch_audit_log",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_branch_audit_log_run_id", table_name="branch_audit_log")
    op.drop_index("ix_branch_audit_log_parent_schema_fqn", table_name="branch_audit_log")
    op.drop_index("ix_branch_audit_log_branch_schema_fqn", table_name="branch_audit_log")
    op.drop_table("branch_audit_log")
