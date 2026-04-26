"""Sprint 73: notebook_cell_run_sources for per-cell run history.

Revision ID: 018
Revises: 017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the per-execute history table for notebook cells.

    Sprint 60's :class:`notebook_cell_runs` table uses a composite PK
    on ``(file_path, cell_id, kernel_session_id)`` and is upserted on
    every execute_request — that gives "current state per session"
    semantics but loses every prior execute's source snapshot, so a
    user who edits + re-runs cannot see what changed between runs.

    Sprint 73 adds a sibling table that records every execute as its
    own row.  Each row carries the source the kernel actually saw +
    the lifecycle status / timestamps + ``execution_count``.  The
    popover in the editor reads ``list_cell_run_sources(...)`` for
    the (file_path, cell_id) pair newest-first and renders a diff
    between consecutive ``source`` snapshots.

    No FK constraint to ``notebook_cell_runs`` — the link is logical
    via the indexed columns.  Cascade-on-delete lives in
    ``notebook_outputs.py`` service (Sprint-67 cascade-via-service
    pattern); a hard FK would force ordering games when the upsert
    on ``notebook_cell_runs`` and the insert here race in the WS
    handler.
    """
    op.create_table(
        "notebook_cell_run_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("cell_id", sa.String(length=64), nullable=False),
        sa.Column("kernel_session_id", sa.String(length=64), nullable=False),
        sa.Column("execution_count", sa.Integer, nullable=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="running",
        ),
    )
    op.create_index(
        "ix_notebook_cell_run_sources_path_cell",
        "notebook_cell_run_sources",
        ["file_path", "cell_id", "started_at"],
    )


def downgrade() -> None:
    """Drop the Sprint-73 per-execute history table."""
    op.drop_index(
        "ix_notebook_cell_run_sources_path_cell",
        table_name="notebook_cell_run_sources",
    )
    op.drop_table("notebook_cell_run_sources")
