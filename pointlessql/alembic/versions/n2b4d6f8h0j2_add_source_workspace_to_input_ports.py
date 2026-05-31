"""phase 162: dp input ports — source_workspace_id for cross-workspace edges

Adds an optional ``source_workspace_id`` foreign key on
``data_product_input_ports``.  Backward-compatible: ``NULL`` means
"same workspace as the consuming data product" — the status quo for
every existing row.  Non-null means the upstream lives in a
different workspace, which the mesh-canvas editor uses to render
cross-workspace edges visually (dashed line + ``[ws: slug]`` badge).

ON DELETE RESTRICT so removing a workspace does not silently sever
cross-workspace lineage edges that consumers may depend on; admin
must explicitly drop the dependency first.

Revision ID: n2b4d6f8h0j2
Revises: m1a3c5e7g9i1
Create Date: 2026-05-31 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n2b4d6f8h0j2"
down_revision: str | None = "m1a3c5e7g9i1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source_workspace_id column + supporting partial index."""
    with op.batch_alter_table("data_product_input_ports") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_workspace_id",
                sa.Integer(),
                sa.ForeignKey(
                    "workspaces.id",
                    name="fk_dp_input_ports_source_workspace",
                    ondelete="RESTRICT",
                ),
                nullable=True,
            )
        )
    op.create_index(
        "ix_dp_input_ports_source_ws",
        "data_product_input_ports",
        ["source_workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop partial index + source_workspace_id column."""
    op.drop_index(
        "ix_dp_input_ports_source_ws",
        table_name="data_product_input_ports",
    )
    with op.batch_alter_table("data_product_input_ports") as batch_op:
        batch_op.drop_column("source_workspace_id")
