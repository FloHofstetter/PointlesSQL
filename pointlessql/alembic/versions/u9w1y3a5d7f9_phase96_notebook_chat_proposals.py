"""phase96 — notebook-cell proposals + cell-provenance audit table

Adds the two tables that back the Phase-96 notebook-editor AI
assistant:

* ``notebook_cell_proposals`` — polymorphic table with an ``action``
  discriminator (``propose`` / ``fix`` / ``explain``).  One row per
  draft from the assistant; status transitions
  ``pending`` → ``accepted`` | ``discarded`` | ``expired``.
  ``explain`` rows are created directly as ``accepted`` (no Run
  button); the explanation is persisted so it survives conversation
  resets and Phase 97 revision history can anchor on it.
* ``notebook_cell_provenance`` — strictly append-only audit table.
  One row per accepted proposal once the user saves the notebook
  and the save-path reconciler has minted the final ``cell_uuid``.
  Phase 97 reads this to render the per-cell agent chain.

Revision ID: u9w1y3a5d7f9
Revises: t8v0x2z4c6e8
Create Date: 2026-05-19 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u9w1y3a5d7f9"
down_revision: str | None = "t8v0x2z4c6e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``notebook_cell_proposals`` + ``notebook_cell_provenance``."""
    op.create_table(
        "notebook_cell_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "proposal_id",
            sa.String(length=36),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "chat_session_id",
            sa.Integer(),
            sa.ForeignKey("editor_chat_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("cell_type", sa.String(length=12), nullable=True),
        sa.Column("target_cell_uuid", sa.String(length=36), nullable=True),
        sa.Column("new_source", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column(
            "position_after_cell_uuid",
            sa.String(length=36),
            nullable=True,
        ),
        sa.Column(
            "position_at_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=12),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("inserted_cell_uuid", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "action IN ('propose', 'fix', 'explain')",
            name="ck_notebook_cell_proposals_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'discarded', 'expired')",
            name="ck_notebook_cell_proposals_status",
        ),
    )
    op.create_index(
        "ix_notebook_cell_proposals_session",
        "notebook_cell_proposals",
        ["chat_session_id", "created_at"],
    )
    op.create_index(
        "ix_notebook_cell_proposals_workspace_status",
        "notebook_cell_proposals",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ux_notebook_cell_proposals_pending_fix",
        "notebook_cell_proposals",
        ["chat_session_id", "action", "target_cell_uuid"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "notebook_cell_provenance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "cell_uuid",
            sa.String(length=36),
            sa.ForeignKey("notebook_cells.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_notebook_cell_provenance_cell",
        "notebook_cell_provenance",
        ["cell_uuid", "created_at"],
    )
    op.create_index(
        "ix_notebook_cell_provenance_run",
        "notebook_cell_provenance",
        ["agent_run_id"],
    )


def downgrade() -> None:
    """Drop the two tables in reverse-FK order."""
    op.drop_index(
        "ix_notebook_cell_provenance_run",
        table_name="notebook_cell_provenance",
    )
    op.drop_index(
        "ix_notebook_cell_provenance_cell",
        table_name="notebook_cell_provenance",
    )
    op.drop_table("notebook_cell_provenance")
    op.drop_index(
        "ux_notebook_cell_proposals_pending_fix",
        table_name="notebook_cell_proposals",
    )
    op.drop_index(
        "ix_notebook_cell_proposals_workspace_status",
        table_name="notebook_cell_proposals",
    )
    op.drop_index(
        "ix_notebook_cell_proposals_session",
        table_name="notebook_cell_proposals",
    )
    op.drop_table("notebook_cell_proposals")
