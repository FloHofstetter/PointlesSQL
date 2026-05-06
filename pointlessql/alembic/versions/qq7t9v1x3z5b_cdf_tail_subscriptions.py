"""cdf_tail_subscriptions + cdf_tail_events for foreign-Delta CDF tail

Phase 40.5 unblocks the deferred Sprint-40.2 sketch: a pull-modell
that complements the Sprint-40.1 push-modell (POST /api/lineage/openlineage).
Admins register one subscription per Delta table they want to tail
the Change Data Feed (CDF) on; a background worker periodically reads
``DeltaTable.load_cdf(starting_version=last+1)`` and records one
row per CDF event into ``cdf_tail_events``.

Two tables, one migration:

* ``cdf_tail_subscriptions`` — opt-in registry: per (workspace, table)
  row identity column convention + advance pointer + pause toggle.
* ``cdf_tail_events`` — captured rows: one row per
  (table, delta_version, row_id, change_type) tuple.  UNIQUE on
  that 4-tuple makes re-tails idempotent.

Storage decision: PointlesSQL metadata DB (small registry +
event-log scoped to opted-in tables).  No new credential surface —
the worker reuses whatever path/credentials soyuz's
``storage_location`` already exposes; tables behind cloud
credentials we don't have stay un-tail-able and the worker logs a
warning rather than failing.

Revision ID: qq7t9v1x3z5b
Revises: pp6r8t0v2x4z
Create Date: 2026-05-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "qq7t9v1x3z5b"
down_revision: str | None = "pp6r8t0v2x4z"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create cdf_tail_subscriptions + cdf_tail_events."""
    op.create_table(
        "cdf_tail_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("table_full_name", sa.String(length=255), nullable=False),
        sa.Column("row_id_column", sa.String(length=128), nullable=False),
        sa.Column("producer_label", sa.String(length=255), nullable=False),
        sa.Column("last_version_processed", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_tailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "table_full_name",
            name="uq_cdf_tail_subscriptions_ws_table",
        ),
    )
    with op.batch_alter_table("cdf_tail_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_cdf_tail_subscriptions_workspace_active",
            ["workspace_id", "is_active"],
            unique=False,
        )

    op.create_table(
        "cdf_tail_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("cdf_tail_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_full_name", sa.String(length=255), nullable=False),
        sa.Column("delta_version", sa.Integer(), nullable=False),
        sa.Column("row_id", sa.String(length=255), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("producer_label", sa.String(length=255), nullable=False),
        sa.Column("commit_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "table_full_name",
            "delta_version",
            "row_id",
            "change_type",
            name="uq_cdf_tail_events_table_version_row_kind",
        ),
        sa.CheckConstraint(
            "change_type IN ('insert','update_preimage','update_postimage','delete')",
            name="ck_cdf_tail_events_change_type",
        ),
    )
    with op.batch_alter_table("cdf_tail_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_cdf_tail_events_table_version",
            ["table_full_name", "delta_version"],
            unique=False,
        )
        batch_op.create_index(
            "ix_cdf_tail_events_row",
            ["table_full_name", "row_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_cdf_tail_events_workspace_created",
            ["workspace_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop cdf_tail_events + cdf_tail_subscriptions."""
    with op.batch_alter_table("cdf_tail_events", schema=None) as batch_op:
        batch_op.drop_index("ix_cdf_tail_events_workspace_created")
        batch_op.drop_index("ix_cdf_tail_events_row")
        batch_op.drop_index("ix_cdf_tail_events_table_version")
    op.drop_table("cdf_tail_events")
    with op.batch_alter_table("cdf_tail_subscriptions", schema=None) as batch_op:
        batch_op.drop_index("ix_cdf_tail_subscriptions_workspace_active")
    op.drop_table("cdf_tail_subscriptions")
