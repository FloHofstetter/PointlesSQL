"""notebook replays

Adds ``notebook_replays`` for the Phase-103 replay / scenario-mode
surface.  Each row records one re-execution of a Phase-97
:class:`NotebookRevision` against today's data; outputs land in
``outputs_json`` and a digest of the cell-by-cell diff lives in
``diff_summary_json``.  ``branch_name`` optionally routes writes to
a Phase-102 Delta-branch so the replay does not corrupt production.

Revision ID: 0107
Revises: 0106
Create Date: 2026-05-20 06:27:21.707188
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0107"
down_revision: str | None = "0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``notebook_replays`` table."""
    op.create_table(
        "notebook_replays",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("replay_uuid", sa.String(length=36), nullable=False),
        sa.Column("notebook_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision_uuid", sa.String(length=36), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outputs_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("diff_summary_json", sa.Text(), nullable=True),
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["notebook_id"], ["notebooks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("replay_uuid", name="uq_notebook_replays_uuid"),
    )
    with op.batch_alter_table("notebook_replays", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notebook_replays_notebook_started",
            ["notebook_id", "started_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop ``notebook_replays``."""
    with op.batch_alter_table("notebook_replays", schema=None) as batch_op:
        batch_op.drop_index("ix_notebook_replays_notebook_started")
    op.drop_table("notebook_replays")
