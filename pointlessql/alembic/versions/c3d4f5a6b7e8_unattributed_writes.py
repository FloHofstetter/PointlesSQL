"""unattributed_writes table for external-write detection (Sprint 14.3)

Adds the persistence layer for the Delta-log scanner that flags
commits whose version is not referenced by any
``agent_run_operations.delta_version_after`` row — i.e. writes that
bypassed every PQL primitive (raw ``deltalake.write_deltalake()``,
Spark, ``cp`` of parquet files, foreign tools).

Detection-only by design.  See
``project_full_autonomous_audit_critical_path.md`` for the
hard-block alternative deferred to Phase 16+.

Revision ID: c3d4f5a6b7e8
Revises: b27e6ad14ead
Create Date: 2026-04-26 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4f5a6b7e8"
down_revision: str | None = "b27e6ad14ead"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "unattributed_writes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("table_fqn", sa.String(length=512), nullable=False),
        sa.Column("delta_version", sa.BigInteger(), nullable=False),
        sa.Column("commit_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_info", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_fqn", "delta_version", name="uq_unattributed_writes_table_ver"),
    )
    with op.batch_alter_table("unattributed_writes", schema=None) as batch_op:
        batch_op.create_index(
            "ix_unattributed_writes_acknowledged_at",
            ["acknowledged_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_unattributed_writes_detected_at",
            ["detected_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("unattributed_writes", schema=None) as batch_op:
        batch_op.drop_index("ix_unattributed_writes_detected_at")
        batch_op.drop_index("ix_unattributed_writes_acknowledged_at")
    op.drop_table("unattributed_writes")
