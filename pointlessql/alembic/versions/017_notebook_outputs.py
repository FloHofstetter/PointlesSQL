"""Sprint 60: notebook_outputs + notebook_cell_runs for editor persistence.

Revision ID: 017
Revises: 016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Phase-12.6 notebook output + cell-run tables.

    DDL is pinned in ADR 0001 — Sprint 58 locked the schema so
    Sprint 60 lands it without any re-design round-trip.  Both
    tables are keyed by the ``(file_path, cell_id,
    kernel_session_id)`` triple; ``notebook_outputs`` adds an
    ``output_index`` so a single cell execution that emits N
    messages lands as N rows in stable order.
    """
    op.create_table(
        "notebook_outputs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("cell_id", sa.String(length=64), nullable=False),
        sa.Column("kernel_session_id", sa.String(length=64), nullable=False),
        sa.Column("output_index", sa.Integer, nullable=False),
        sa.Column("msg_type", sa.String(length=32), nullable=False),
        sa.Column("mime_bundle", sa.Text, nullable=False),
        sa.Column("output_metadata", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "file_path", "cell_id", "kernel_session_id", "output_index",
            name="uq_notebook_outputs_position",
        ),
    )
    op.create_index(
        "ix_notebook_outputs_lookup",
        "notebook_outputs",
        ["file_path", "cell_id"],
    )
    op.create_table(
        "notebook_cell_runs",
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("cell_id", sa.String(length=64), nullable=False),
        sa.Column("kernel_session_id", sa.String(length=64), nullable=False),
        sa.Column("execution_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "file_path", "cell_id", "kernel_session_id",
            name="pk_notebook_cell_runs",
        ),
    )


def downgrade() -> None:
    """Drop the Phase-12.6 output persistence tables."""
    op.drop_table("notebook_cell_runs")
    op.drop_index("ix_notebook_outputs_lookup", table_name="notebook_outputs")
    op.drop_table("notebook_outputs")
