"""phase 129: product lifecycle state

Adds four columns to ``data_products`` that turn the product from a
stateless metadata row into an operational artefact with a formal
state machine (``draft → active → deprecated → retired → archived``,
``archived → active`` restore, ``active → archived`` shortcut):

- ``lifecycle_state`` String(16) NOT NULL default ``'active'``.
- ``lifecycle_changed_at`` DateTime, nullable.
- ``lifecycle_changed_by_user_id`` Integer FK ``users.id``, nullable.
- ``replacement_data_product_id`` Integer FK ``data_products.id``,
  nullable (set when a retired product names its successor).

Backfill: existing rows are stamped ``'active'`` via the column
default — no UPDATE needed.  SQLite uses ``batch_alter_table`` with
explicitly-named FKs (matches the Phase-124 ``domain_id`` pattern).

Revision ID: k2m4o6q8s0u2
Revises: j1l3n5p7r9t1
Create Date: 2026-05-29 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k2m4o6q8s0u2"
down_revision: str | None = "j1l3n5p7r9t1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the four lifecycle columns + the check + index."""
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "lifecycle_state",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(
            sa.Column("lifecycle_changed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "lifecycle_changed_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", name="fk_data_products_lifecycle_changed_by"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "replacement_data_product_id",
                sa.Integer(),
                sa.ForeignKey("data_products.id", name="fk_data_products_replacement"),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_data_products_lifecycle_state",
            "lifecycle_state IN ('draft','active','deprecated','retired','archived')",
        )
    op.create_index(
        "ix_data_products_lifecycle_state",
        "data_products",
        ["lifecycle_state"],
    )


def downgrade() -> None:
    """Drop the four lifecycle columns + the check + index."""
    op.drop_index("ix_data_products_lifecycle_state", table_name="data_products")
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.drop_constraint("ck_data_products_lifecycle_state", type_="check")
        batch_op.drop_column("replacement_data_product_id")
        batch_op.drop_column("lifecycle_changed_by_user_id")
        batch_op.drop_column("lifecycle_changed_at")
        batch_op.drop_column("lifecycle_state")
