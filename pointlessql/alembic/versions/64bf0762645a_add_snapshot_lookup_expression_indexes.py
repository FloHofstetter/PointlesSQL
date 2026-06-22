"""add snapshot lookup expression indexes

The dashboard-snapshot and table-profile-snapshot models each declare a
covering ``captured_at DESC`` expression index for their "latest
snapshot per entity" lookups, but the migrations that created the
tables omitted the indexes.  SQLite cannot reflect expression indexes,
so ``alembic check`` silently skipped the mismatch; Postgres reflects
them and reports the models as drifted.  Create the two missing
indexes so the schema matches the ORM metadata on both dialects.

Revision ID: 64bf0762645a
Revises: d118521b6c15
Create Date: 2026-06-21 23:35:16.645735
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64bf0762645a"
down_revision: str | None = "d118521b6c15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the two ``captured_at DESC`` snapshot-lookup indexes."""
    op.create_index(
        "ix_bi_dashboard_snapshots_dashboard_captured",
        "bi_dashboard_snapshots",
        ["dashboard_id", sa.text("captured_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_table_profile_snapshots_lookup",
        "table_profile_snapshots",
        ["monitor_id", "table_fqn", sa.text("captured_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop the snapshot-lookup indexes."""
    op.drop_index(
        "ix_table_profile_snapshots_lookup",
        table_name="table_profile_snapshots",
    )
    op.drop_index(
        "ix_bi_dashboard_snapshots_dashboard_captured",
        table_name="bi_dashboard_snapshots",
    )
