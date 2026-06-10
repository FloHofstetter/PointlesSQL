"""phase 130: input-port consumption enforcement (D2)

Turns the declared upstream input-ports introduced in Phase 125 into an
*enforceable* contract.  Adds a single per-policy field that selects
whether reads taking place "in the context of a consuming product" are:

* ``off``      — not checked,
* ``advisory`` — allowed but warned + audited (the default),
* ``strict``   — blocked when the source is not declared as an input.

Two columns added (one per policy table; same enum + check):

- ``workspace_governance_policies.consumption_enforcement`` String(16)
  NOT NULL default ``'advisory'`` — workspace baseline.
- ``data_product_policies.consumption_enforcement`` String(16) nullable
  — per-product override that ``NULL`` means "inherit workspace".

Backfill via the column server-default — existing workspace rows get
``'advisory'`` (matching the cluster's "honest split" default), product
override rows stay ``NULL`` (inherit).

Revision ID: l3n5p7r9t1v3
Revises: k2m4o6q8s0u2
Create Date: 2026-05-29 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l3n5p7r9t1v3"
down_revision: str | None = "k2m4o6q8s0u2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VALID_MODES = "consumption_enforcement IN ('off','advisory','strict')"


def upgrade() -> None:
    """Add the per-policy ``consumption_enforcement`` columns + checks."""
    with op.batch_alter_table("workspace_governance_policies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "consumption_enforcement",
                sa.String(length=16),
                nullable=False,
                server_default="advisory",
            )
        )
        batch_op.create_check_constraint(
            "ck_workspace_governance_policies_consumption", _VALID_MODES
        )
    with op.batch_alter_table("data_product_policies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "consumption_enforcement",
                sa.String(length=16),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_data_product_policies_consumption",
            "consumption_enforcement IS NULL OR " + _VALID_MODES,
        )


def downgrade() -> None:
    """Drop the per-policy ``consumption_enforcement`` columns + checks."""
    with op.batch_alter_table("data_product_policies", schema=None) as batch_op:
        batch_op.drop_constraint("ck_data_product_policies_consumption", type_="check")
        batch_op.drop_column("consumption_enforcement")
    with op.batch_alter_table("workspace_governance_policies", schema=None) as batch_op:
        batch_op.drop_constraint("ck_workspace_governance_policies_consumption", type_="check")
        batch_op.drop_column("consumption_enforcement")
