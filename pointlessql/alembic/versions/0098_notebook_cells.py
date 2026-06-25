"""notebook_cells stable-identity table

Phase 95 introduces cell-level social rows (comments, reactions,
follows, tags).  The existing per-cell DB tables (``notebook_outputs``,
``notebook_cell_runs``, ``notebook_cell_run_sources``) key on
``content_hash`` which changes on every meaningful edit — useless as
a social anchor.  This migration creates ``notebook_cells``, a thin
mapping from a stable UUID to the cell's *current* content_hash that
the save-path reconciler updates in place.

The on-disk ``.py`` marker grammar stays IDE-agnostic (no UUID
sidecar tokens); the UUID lives only in this table.

Revision ID: 0098
Revises: 0097
Create Date: 2026-05-19 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0098"
down_revision: str | None = "0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_cells`` table + supporting indexes."""
    op.create_table(
        "notebook_cells",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "notebook_id",
            sa.String(length=36),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("current_content_hash", sa.String(length=64), nullable=False),
        sa.Column("ordinal_hint", sa.Integer(), nullable=False),
        sa.Column("last_source_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_notebook_cells"),
        sa.CheckConstraint("ordinal_hint >= 0", name="ck_notebook_cells_ordinal_hint"),
    )
    op.create_index(
        "ix_notebook_cells_live_ordinal",
        "notebook_cells",
        ["notebook_id", "removed_at", "ordinal_hint"],
    )
    op.create_index(
        "ix_notebook_cells_notebook_hash",
        "notebook_cells",
        ["notebook_id", "current_content_hash"],
    )


def downgrade() -> None:
    """Drop ``notebook_cells`` + its indexes."""
    op.drop_index("ix_notebook_cells_notebook_hash", table_name="notebook_cells")
    op.drop_index("ix_notebook_cells_live_ordinal", table_name="notebook_cells")
    op.drop_table("notebook_cells")
