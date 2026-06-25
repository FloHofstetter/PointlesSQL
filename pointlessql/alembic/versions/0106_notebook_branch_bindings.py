"""notebook branch bindings

Adds ``notebook_branch_bindings`` so a notebook can declare it
writes to a Delta-branch instead of the canonical ``main`` table
state.  Promotion is a separate human-reviewed step (see Phase-102
shoreguard gate); the table tracks both lifecycle states.

Revision ID: 0106
Revises: 0105
Create Date: 2026-05-20 06:22:19.379468
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0106"
down_revision: str | None = "0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notebook_branch_bindings`` table."""
    op.create_table(
        "notebook_branch_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("base_revision_uuid", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["promoted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notebook_branch_bindings", schema=None) as batch_op:
        batch_op.create_index("ix_nb_branch_binding_branch", ["branch_name"], unique=False)
        batch_op.create_index(
            "ix_nb_branch_binding_notebook_active",
            ["notebook_id", "superseded_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notebook_branch_bindings``."""
    with op.batch_alter_table("notebook_branch_bindings", schema=None) as batch_op:
        batch_op.drop_index("ix_nb_branch_binding_notebook_active")
        batch_op.drop_index("ix_nb_branch_binding_branch")
    op.drop_table("notebook_branch_bindings")
