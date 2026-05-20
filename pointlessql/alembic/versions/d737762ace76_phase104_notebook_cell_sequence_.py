"""phase104 — notebook cell sequence proposals

Adds the ``notebook_cell_sequence_proposals`` table backing Phase
104's NL→Notebook code-gen flow.  Extends the Phase-96 single-cell
proposal surface to multi-cell sequences so a prompt can yield a
coherent ``imports → DataFrame → plot → markdown`` block that the
user inserts atomically.

Revision ID: d737762ace76
Revises: 311c87f25421
Create Date: 2026-05-20 06:33:06.866716
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d737762ace76"
down_revision: str | None = "311c87f25421"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_cell_sequence_proposals``."""
    op.create_table(
        "notebook_cell_sequence_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("cells_json", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=12),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["chat_session_id"], ["editor_chat_sessions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposal_id", name="uq_nb_cell_sequence_proposal_uuid"
        ),
    )
    with op.batch_alter_table(
        "notebook_cell_sequence_proposals", schema=None
    ) as batch_op:
        batch_op.create_index(
            "ix_nb_cell_sequence_session",
            ["chat_session_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notebook_cell_sequence_proposals``."""
    with op.batch_alter_table(
        "notebook_cell_sequence_proposals", schema=None
    ) as batch_op:
        batch_op.drop_index("ix_nb_cell_sequence_session")
    op.drop_table("notebook_cell_sequence_proposals")
