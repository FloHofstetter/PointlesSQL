"""notebook cell authorship

Adds the ``notebook_cell_authorship`` table used by the Phase-101
cell-attribution chip + reviewer-per-cell flow.

One row per :class:`NotebookCellIdentity.id` tracks who minted the
cell (``first_author_*``) and who last edited it
(``last_modifier_*``).  The kind columns flip between ``"user"`` and
``"agent"``; user authors record the email, agent authors record the
``agents.id`` FK + an optional ``agent_run_id`` snapshot that ties
the cell back to the originating run (Phase 103 replay hook).

Distinct from the Phase-96 :class:`NotebookCellProvenance` table —
provenance is strictly append-only audit; this table is the *current*
attribution surface (1:1 with the cell), upserted by the save-path
reconciler.

Revision ID: 0103
Revises: 0102
Create Date: 2026-05-20 00:50:58.122396
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: str | None = "0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_cell_authorship`` + supporting indexes."""
    op.create_table(
        "notebook_cell_authorship",
        sa.Column("cell_uuid", sa.String(length=36), nullable=False),
        sa.Column("first_author_kind", sa.String(length=8), nullable=False),
        sa.Column("first_author_email", sa.String(length=255), nullable=True),
        sa.Column("first_author_agent_id", sa.Integer(), nullable=True),
        sa.Column("first_author_agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_modifier_kind", sa.String(length=8), nullable=False),
        sa.Column("last_modifier_email", sa.String(length=255), nullable=True),
        sa.Column("last_modifier_agent_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_modified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cell_uuid"], ["notebook_cells.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_author_agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["last_modifier_agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("cell_uuid"),
    )
    with op.batch_alter_table("notebook_cell_authorship", schema=None) as batch_op:
        batch_op.create_index(
            "ix_cell_authorship_first_agent",
            ["first_author_agent_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_cell_authorship_last_agent",
            ["last_modifier_agent_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notebook_cell_authorship`` + its indexes."""
    with op.batch_alter_table("notebook_cell_authorship", schema=None) as batch_op:
        batch_op.drop_index("ix_cell_authorship_last_agent")
        batch_op.drop_index("ix_cell_authorship_first_agent")
    op.drop_table("notebook_cell_authorship")
