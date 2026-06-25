"""tag_policy_rules add scope

Lifts a tag-policy rule from deployment-global to an optional Unity-
Catalog subtree scope so one rule can govern every matching table
beneath a catalog or schema without per-table config.  ``scope_type``
defaults to ``global`` (server default backfills existing rows), and a
CHECK constraint pins it to the known scope kinds; ``scope_value`` holds
the catalog (one part) or schema (two parts) name, NULL for global.

Revision ID: 0162
Revises: 0161
Create Date: 2026-06-20 21:32:05.558096
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0162"
down_revision: str | None = "0161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``scope_type`` / ``scope_value`` columns + scope CHECK."""
    with op.batch_alter_table("tag_policy_rules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scope_type", sa.String(length=16), server_default="global", nullable=False)
        )
        batch_op.add_column(sa.Column("scope_value", sa.String(length=512), nullable=True))
        batch_op.create_check_constraint(
            "ck_tag_policy_rules_scope_type",
            "scope_type IN ('global', 'catalog', 'schema')",
        )


def downgrade() -> None:
    """Drop the scope CHECK constraint and both scope columns."""
    with op.batch_alter_table("tag_policy_rules", schema=None) as batch_op:
        batch_op.drop_constraint("ck_tag_policy_rules_scope_type", type_="check")
        batch_op.drop_column("scope_value")
        batch_op.drop_column("scope_type")
