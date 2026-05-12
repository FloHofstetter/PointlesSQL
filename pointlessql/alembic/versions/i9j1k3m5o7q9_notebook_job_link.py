"""notebook_job_link table (Phase 67.4)

Adds a thin mapping table so the Phase-67 notebook editor can list
``Jobs of this notebook`` without doing a ``WHERE config LIKE
'%notebook_path%'`` scan on every editor open. One row per
(notebook_path, job_id) pair; written opportunistically by the
``POST /api/jobs`` + ``POST /api/notebooks/run-once`` handlers when
``kind == "papermill"``.

The table is purely an index — every fact is also derivable from the
``Job.config`` JSON blob; if a row goes stale the worst case is the
editor panel showing a phantom entry that the user can ignore. We
choose the index trade-off over JSON-scan because Postgres + SQLite
have no portable JSON-path index that would speed up the LIKE.

Revision ID: i9j1k3m5o7q9
Revises: hh7i9k1m3o5q
Create Date: 2026-05-12 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i9j1k3m5o7q9"
down_revision: str | None = "hh7i9k1m3o5q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the notebook_job_link mapping table."""
    op.create_table(
        "notebook_job_link",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("notebook_path", sa.String(length=1024), nullable=False),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_notebook_job_link_path",
        "notebook_job_link",
        ["notebook_path"],
    )
    op.create_index(
        "ix_notebook_job_link_workspace_path",
        "notebook_job_link",
        ["workspace_id", "notebook_path"],
    )
    op.create_index(
        "ix_notebook_job_link_job_id",
        "notebook_job_link",
        ["job_id"],
    )


def downgrade() -> None:
    """Drop the notebook_job_link mapping table."""
    op.drop_index("ix_notebook_job_link_job_id", table_name="notebook_job_link")
    op.drop_index(
        "ix_notebook_job_link_workspace_path",
        table_name="notebook_job_link",
    )
    op.drop_index("ix_notebook_job_link_path", table_name="notebook_job_link")
    op.drop_table("notebook_job_link")
