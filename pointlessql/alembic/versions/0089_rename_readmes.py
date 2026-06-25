"""rename data_product_readmes to entity_readmes.

Phase 77.0.B added the polymorphic ``social_target_id`` anchor
to the README table.  Since then every reader could route
through it, but the historical DP-only PK + the ``data_product_id``
column survived for back-compat.  Phase 78 polish completes the
rename:

* ``data_product_readmes`` → ``entity_readmes``
* Drop the nullable ``data_product_id`` column.
* Swap the legacy UNIQUE ``uq_dp_readme_versioned`` (which keyed
  on ``data_product_id``) for ``uq_entity_readme_versioned`` on
  ``(workspace_id, social_target_id, version_int)`` — the
  polymorphic kind-agnostic version key.
* Rename the two indexes (``ix_dp_readme_dp_version`` →
  ``ix_entity_readmes_target_version``; the social-target index
  stays semantically identical but follows the new naming).

Downgrade restores the legacy table name + column.  The
``data_product_id`` values come from the social_targets back-
pointer for ``kind='dp'`` rows; non-DP READMEs lose the column
(they never had a useful value anyway).

Revision ID: 0089
Revises: 0088
Create Date: 2026-05-16 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0089"
down_revision: str | None = "0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename + drop the legacy DP-only column on the README table."""
    op.rename_table("data_product_readmes", "entity_readmes")
    with op.batch_alter_table("entity_readmes") as batch:
        batch.drop_constraint("uq_dp_readme_versioned", type_="unique")
        batch.drop_index("ix_dp_readme_dp_version")
        batch.drop_index("ix_data_product_readmes_social_target")
        batch.drop_column("data_product_id")
        batch.create_unique_constraint(
            "uq_entity_readme_versioned",
            ["workspace_id", "social_target_id", "version_int"],
        )
        batch.create_index(
            "ix_entity_readmes_target_version",
            ["social_target_id", "version_int"],
        )
        batch.create_index(
            "ix_entity_readmes_social_target",
            ["social_target_id"],
        )


def downgrade() -> None:
    """Reinstate ``data_product_readmes`` + the legacy DP column."""
    with op.batch_alter_table("entity_readmes") as batch:
        batch.drop_index("ix_entity_readmes_social_target")
        batch.drop_index("ix_entity_readmes_target_version")
        batch.drop_constraint("uq_entity_readme_versioned", type_="unique")
        batch.add_column(
            sa.Column(
                "data_product_id",
                sa.Integer(),
                sa.ForeignKey(
                    "data_products.id",
                    name="fk_entity_readmes_data_product_id",
                    ondelete="CASCADE",
                ),
                nullable=True,
            )
        )
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE entity_readmes "
            "SET data_product_id = ("
            "    SELECT st.data_product_id "
            "    FROM social_targets st "
            "    WHERE st.id = entity_readmes.social_target_id "
            "      AND st.entity_kind = 'dp'"
            ")"
        )
    )
    with op.batch_alter_table("entity_readmes") as batch:
        batch.create_unique_constraint(
            "uq_dp_readme_versioned",
            ["workspace_id", "data_product_id", "version_int"],
        )
        batch.create_index(
            "ix_dp_readme_dp_version",
            ["data_product_id", "version_int"],
        )
        batch.create_index(
            "ix_data_product_readmes_social_target",
            ["social_target_id"],
        )
    op.rename_table("entity_readmes", "data_product_readmes")
