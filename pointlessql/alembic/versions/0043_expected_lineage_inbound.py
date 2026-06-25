"""expected_lineage_inbound: registry of expected upstream OL producers

Phase 40 Sprint 40.4 introduces ``expected_lineage_inbound`` to
register "table T should receive at least one inbound OpenLineage
event from producer P every N minutes".  The Sprint-40.3 table-
detail card consults this registry to surface a per-producer
freshness status (green/yellow/red) and the admin
``/admin/expected-producers`` page exposes CRUD on the rows.

Three uniqueness invariants:

* ``(workspace_id, target_table_full_name, producer)`` is UNIQUE so
  the registry never carries duplicate expectations.
* ``max_silence_minutes`` is a positive integer (CHECK).
* ``is_active`` defaults TRUE so a freshly-registered expectation
  immediately participates in freshness checks.

Revision ID: 0043
Revises: 0042
Create Date: 2026-05-06 23:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create expected_lineage_inbound."""
    op.create_table(
        "expected_lineage_inbound",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("target_table_full_name", sa.String(length=255), nullable=False),
        sa.Column("producer", sa.String(length=255), nullable=False),
        sa.Column("max_silence_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "target_table_full_name",
            "producer",
            name="uq_expected_lineage_inbound_ws_table_producer",
        ),
        sa.CheckConstraint(
            "max_silence_minutes > 0",
            name="ck_expected_lineage_inbound_silence_positive",
        ),
    )
    with op.batch_alter_table("expected_lineage_inbound", schema=None) as batch_op:
        batch_op.create_index(
            "ix_expected_lineage_inbound_workspace_active",
            ["workspace_id", "is_active"],
            unique=False,
        )
        batch_op.create_index(
            "ix_expected_lineage_inbound_target",
            ["target_table_full_name"],
            unique=False,
        )


def downgrade() -> None:
    """Drop expected_lineage_inbound."""
    with op.batch_alter_table("expected_lineage_inbound", schema=None) as batch_op:
        batch_op.drop_index("ix_expected_lineage_inbound_target")
        batch_op.drop_index("ix_expected_lineage_inbound_workspace_active")
    op.drop_table("expected_lineage_inbound")
