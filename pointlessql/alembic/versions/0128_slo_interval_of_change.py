"""interval-of-change SLO + mesh-health MVP (G1/G2)

Adds ``'interval_of_change'`` to the SLO kind CHECK constraint so the
new measurable kind can be declared.  No new tables, no new columns —
the kind is evaluated from the existing
``data_product_contract_events`` write-event log.

Revision ID: 0128
Revises: 0127
Create Date: 2026-05-30 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0128"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_CHECK = (
    "slo_kind IN ('freshness','timeliness','completeness','volume',"
    "'statistical_shape','lineage','precision_accuracy','availability',"
    "'performance','interval_of_change')"
)

_OLD_CHECK = (
    "slo_kind IN ('freshness','timeliness','completeness','volume',"
    "'statistical_shape','lineage','precision_accuracy','availability',"
    "'performance')"
)


def upgrade() -> None:
    """Replace the kind CHECK to accept ``interval_of_change``."""
    with op.batch_alter_table("data_product_slos") as batch:
        batch.drop_constraint("ck_dp_slos_kind", type_="check")
        batch.create_check_constraint("ck_dp_slos_kind", _NEW_CHECK)


def downgrade() -> None:
    """Restore the pre-138 kind CHECK."""
    with op.batch_alter_table("data_product_slos") as batch:
        batch.drop_constraint("ck_dp_slos_kind", type_="check")
        batch.create_check_constraint("ck_dp_slos_kind", _OLD_CHECK)
